"""Isolated raw-MIDI preset experiment; it deliberately does not alter Portrait."""

from __future__ import annotations

import asyncio
import random
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

import mido

from app.music.generation.emotion_window import EmotionWindowAggregator
from app.music.schemas import EmotionState, MusicEvent, MusicSegment, SegmentNote, TrackConfig


@dataclass(frozen=True)
class RawNote:
    beat: float
    duration: float
    pitch: int
    velocity: int


@dataclass(frozen=True)
class MotherPiece:
    id: str
    emotion: str
    path: Path
    bpm: int
    meter: str
    beats_per_bar: int
    bars: int
    notes: tuple[RawNote, ...]
    phrase_starts: tuple[float, ...]
    anchor_beats: frozenset[float]


class PresetsTestingLibrary:
    """Accept only the 50 original ``<emotion>_<id>.mid`` sources."""

    EMOTIONS = ("calm", "joy", "neutral", "sad", "tense")
    SOURCE_RE = re.compile(r"^(calm|joy|neutral|sad|tense)_\d{3}\.mid$")
    EXPECTED_COUNT = 50

    def __init__(self, root: Path) -> None:
        self.root = root / "motifs"
        self.sources = self._discover()

    def _discover(self) -> list[Path]:
        files = [path for path in sorted(self.root.glob("*/*.mid")) if self.SOURCE_RE.match(path.name)]
        if len(files) != self.EXPECTED_COUNT:
            raise ValueError(f"preset experiment requires exactly {self.EXPECTED_COUNT} original MIDI sources; found {len(files)}")
        if {path.parent.name for path in files} != set(self.EMOTIONS):
            raise ValueError("preset experiment source emotions are incomplete")
        return files

    def choose(self, emotion: str, rng: random.Random) -> MotherPiece:
        candidates = [path for path in self.sources if path.parent.name == emotion]
        return self.analyze(rng.choice(candidates))

    @staticmethod
    def analyze(path: Path) -> MotherPiece:
        midi = mido.MidiFile(path)
        tempo = 500000
        numerator, denominator = 4, 4
        active: dict[tuple[int, int], tuple[int, int]] = {}
        notes: list[RawNote] = []
        absolute = 0
        for message in mido.merge_tracks(midi.tracks):
            absolute += message.time
            if message.type == "set_tempo":
                tempo = message.tempo
            elif message.type == "time_signature":
                numerator, denominator = message.numerator, message.denominator
            elif message.type == "note_on" and message.velocity:
                active[(message.channel, message.note)] = (absolute, message.velocity)
            elif message.type in {"note_off", "note_on"} and hasattr(message, "note"):
                started = active.pop((message.channel, message.note), None)
                if started:
                    onset, velocity = started
                    notes.append(RawNote(round(onset / midi.ticks_per_beat, 3), max(.125, round((absolute - onset) / midi.ticks_per_beat, 3)), message.note, velocity))
        if not notes:
            raise ValueError(f"raw preset has no notes: {path.name}")
        notes.sort(key=lambda note: (note.beat, note.pitch))
        beats_per_bar = round(numerator * 4 / denominator)
        total_beats = max(note.beat + note.duration for note in notes)
        bars = max(4, int((total_beats + beats_per_bar - 1) // beats_per_bar))
        # A four-bar grid is always safe; strong long/on-bar notes become theme anchors.
        phrase_starts = tuple(float(beat) for beat in range(0, bars * beats_per_bar, 4 * beats_per_bar))
        anchors = frozenset(note.beat for note in notes if note.beat % beats_per_bar == 0 or note.duration >= 1.5)
        return MotherPiece(path.stem, path.parent.name, path, round(mido.tempo2bpm(tempo)), f"{numerator}/{denominator}", beats_per_bar, bars, tuple(notes), phrase_starts, anchors)


class PresetsTestingRuntime:
    """Plays one selected mother piece in contiguous four-bar windows."""

    WINDOW_BARS = 4
    MAX_BPM_STEP = 8

    def __init__(self, library: PresetsTestingLibrary, tracks: list[TrackConfig], model: Any, dispatch: Callable[[MusicEvent], None], all_notes_off: Callable[[], None], broadcast: Callable[[dict], Awaitable[None]]) -> None:
        self.library, self.tracks, self.model = library, tracks, model
        self.dispatch, self.all_notes_off, self.broadcast = dispatch, all_notes_off, broadcast
        self.aggregator = EmotionWindowAggregator(16, 4)
        self.task: asyncio.Task | None = None
        self.piece: MotherPiece | None = None
        self.cursor = 0.0
        self.current_emotion = "neutral"
        self.current_bpm = 84
        self.last_segment: MusicSegment | None = None
        self.fallback_count = 0
        self.generation_error = ""
        self.rule_percussion_count = 0
        self.notochord_percussion_count = 0
        self.dispatch_tasks: set[asyncio.Task] = set()
        self.rng = random.Random()

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def add_emotion(self, emotion: EmotionState) -> None:
        if emotion.confidence >= .45:
            self.aggregator.add(emotion)

    def start(self) -> None:
        if self.running:
            return
        self.piece = None
        self.cursor = 0.0
        self.fallback_count = self.rule_percussion_count = self.notochord_percussion_count = 0
        self.generation_error = ""
        self.task = asyncio.create_task(self._run(), name="presets-testing-runtime")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        for task in tuple(self.dispatch_tasks):
            task.cancel()
        if self.dispatch_tasks:
            await asyncio.gather(*self.dispatch_tasks, return_exceptions=True)
        self.dispatch_tasks.clear()
        self.last_segment = None
        self.all_notes_off()

    def status(self) -> dict[str, Any]:
        piece = self.piece
        return {"running": self.running, "type": "presets_testing", "initial_emotion_ready": piece is not None,
                "raw_preset_id": piece.id if piece else "", "raw_preset_path": str(piece.path) if piece else "",
                "raw_meter": piece.meter if piece else "", "raw_bpm": piece.bpm if piece else None,
                "window_start_beat": self.cursor, "window_bars": self.WINDOW_BARS, "current_bpm": self.current_bpm,
                "current_emotion": self.current_emotion, "source_locked": piece is not None,
                "raw_phrase_boundaries": list(piece.phrase_starts) if piece else [], "theme_anchor_count": len(piece.anchor_beats) if piece else 0,
                "rule_percussion_count": self.rule_percussion_count, "notochord_percussion_count": self.notochord_percussion_count,
                "fallback_count": self.fallback_count, "generation_error": self.generation_error}

    async def _run(self) -> None:
        while self.aggregator.sample_count() < 4:
            await asyncio.sleep(.1)
        initial = self.aggregator.aggregate()
        self.piece = self.library.choose(initial.label, self.rng)
        self.current_emotion, self.current_bpm = initial.label, self.piece.bpm
        while True:
            emotion = self.aggregator.aggregate()
            segment = self.compose_window(emotion)
            self.last_segment = segment
            await self.broadcast({"kind": "presets_testing_segment_started", "segment": segment.model_dump(), "presets_testing": self.status()})
            tasks = self._schedule(segment)
            await asyncio.sleep(segment.duration_seconds)
            await asyncio.gather(*tasks, return_exceptions=True)
            self.dispatch_tasks.difference_update(tasks)
            self.cursor = (self.cursor + self.WINDOW_BARS * self.piece.beats_per_bar) % (self.piece.bars * self.piece.beats_per_bar)

    def compose_window(self, emotion: EmotionState) -> MusicSegment:
        assert self.piece is not None
        target = self.piece.bpm + {"sad": -10, "calm": -5, "neutral": 0, "joy": 7, "tense": 10}[emotion.label]
        bpm = max(self.current_bpm - self.MAX_BPM_STEP, min(self.current_bpm + self.MAX_BPM_STEP, target))
        window_beats = self.WINDOW_BARS * self.piece.beats_per_bar
        melody = next((track for track in self.tracks if track.enabled and track.compute_enabled and track.role == "melody"), None)
        if melody is None:
            raise ValueError("presets testing needs an enabled melody track")
        notes: list[SegmentNote] = []
        for raw in self.piece.notes:
            relative = (raw.beat - self.cursor) % (self.piece.bars * self.piece.beats_per_bar)
            if relative >= window_beats:
                continue
            anchor = raw.beat in self.piece.anchor_beats
            # The experiment currently keeps the authored key (transpose = 0).
            # This is always within the +/-2 policy and avoids unsafe same-key remapping.
            pitch = raw.pitch
            velocity = raw.velocity if anchor else max(melody.velocity_range[0], min(melody.velocity_range[1], round(raw.velocity * (.8 + emotion.arousal_norm * .35))))
            notes.append(SegmentNote(beat=round(relative, 3), duration_beats=min(raw.duration, window_beats - relative), pitch=pitch, velocity=velocity, track_id=melody.id, channel=melody.midi_channel, voice_role="theme", generated_by="rule"))
        notes.extend(self._percussion(notes, emotion, window_beats))
        segment = MusicSegment(id=uuid.uuid4().hex[:12], emotion=emotion.label, previous_emotion=self.current_emotion, bpm=bpm, bars=self.WINDOW_BARS, beats_per_bar=self.piece.beats_per_bar, root_note="C", scale="raw", source="portrait", form_section="theme", phrase_id=f"{self.piece.id}:{int(self.cursor)}", portrait_asset_id=self.piece.id, portrait_asset_title=self.piece.path.name, notes=notes, drum_note_count=sum(note.track_id.startswith("drum") for note in notes), cymbal_note_count=sum(note.track_id.startswith("cymbal") for note in notes))
        self.current_emotion, self.current_bpm = emotion.label, bpm
        return self._assist_accompaniment(segment)

    def _percussion(self, melody: list[SegmentNote], emotion: EmotionState, window_beats: float) -> list[SegmentNote]:
        by_role = {track.role: track for track in self.tracks if track.enabled and track.compute_enabled}
        notes: list[SegmentNote] = []
        onsets = {round(note.beat, 3) for note in melody}
        for role, preferred in (("drum", ("kick", "snare", "closed_hat")), ("cymbal", ("closed_hat", "crash", "ride"))):
            track = by_role.get(role)
            if not track:
                continue
            legal = list((getattr(track, "drum_notes", {}) or {}).values()) or list(range(track.pitch_range[0], track.pitch_range[1] + 1))
            for index, beat in enumerate(sorted(onsets)):
                if beat >= window_beats or (role == "cymbal" and beat % self.piece.beats_per_bar != 0):
                    continue
                pitch = legal[index % len(legal)]
                notes.append(SegmentNote(beat=beat, duration_beats=.25, pitch=pitch, velocity=min(track.velocity_range[1], 55 + round(emotion.arousal_norm * 45)), track_id=track.id, channel=track.midi_channel, generated_by="rule", notochord_eligible=True))
        self.rule_percussion_count = len(notes)
        return notes

    def _assist_accompaniment(self, segment: MusicSegment) -> MusicSegment:
        try:
            assisted = self.model.assist_portrait_segment(segment, self.tracks)
            # The experiment accepts only unchanged authored xylophone notes and legal percussion.
            original_theme = [(n.beat, n.pitch, n.velocity, n.duration_beats) for n in segment.notes if n.voice_role == "theme"]
            result_theme = [(n.beat, n.pitch, n.velocity, n.duration_beats) for n in assisted.notes if n.voice_role == "theme"]
            legal = {track.id: set((getattr(track, "drum_notes", {}) or {}).values()) for track in self.tracks if track.role in {"drum", "cymbal"}}
            if original_theme != result_theme or any(note.track_id in legal and legal[note.track_id] and note.pitch not in legal[note.track_id] for note in assisted.notes):
                raise ValueError("assistant changed protected material")
            self.notochord_percussion_count = sum(note.generated_by == "notochord" and note.track_id in legal for note in assisted.notes)
            return assisted
        except Exception as exc:
            self.fallback_count += 1
            self.generation_error = f"Notochord fallback: {exc}"
            self.notochord_percussion_count = 0
            return segment

    def _schedule(self, segment: MusicSegment) -> list[asyncio.Task]:
        seconds_per_beat = 60 / segment.bpm
        async def play(note: SegmentNote) -> None:
            await asyncio.sleep(note.beat * seconds_per_beat)
            self.dispatch(MusicEvent(track_id=note.track_id, type="note_on", pitch=note.pitch, velocity=note.velocity, duration_ms=round(note.duration_beats * seconds_per_beat * 1000), channel=note.channel))
            await asyncio.sleep(note.duration_beats * seconds_per_beat)
            self.dispatch(MusicEvent(track_id=note.track_id, type="note_off", pitch=note.pitch, velocity=0, duration_ms=0, channel=note.channel))
        tasks = [asyncio.create_task(play(note)) for note in segment.notes]
        self.dispatch_tasks.update(tasks)
        return tasks
