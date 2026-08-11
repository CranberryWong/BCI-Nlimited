"""A deliberately pure, sound-first Notochord ensemble experiment.

The model writes every audible note.  Emotion is deliberately a light-touch
performance control (tempo and dynamics), not a harmonic, scale, or motif
gate: listening quality comes first while we establish the musical baseline.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.music.generation.emotion_window import EmotionWindowAggregator
from app.music.generation.portrait_library import PortraitAsset, PortraitLibrary
from app.music.schemas import ActiveMusicConfig, EmotionState, MusicEvent, MusicSegment, SegmentNote, TrackConfig


class NotoTestingRuntime:
    """Continuously let Notochord write a full ensemble on enabled tracks."""

    WINDOW_BARS = 4
    MAX_EVENTS_PER_WINDOW = 512

    def __init__(
        self,
        library: PortraitLibrary,
        config: ActiveMusicConfig,
        model: Any,
        dispatch: Callable[[MusicEvent], None],
        all_notes_off: Callable[[], None],
        broadcast: Callable[[dict], Awaitable[None]],
    ) -> None:
        self.library, self.config, self.model = library, config, model
        self.dispatch, self.all_notes_off, self.broadcast = dispatch, all_notes_off, broadcast
        self.aggregator = EmotionWindowAggregator(16, 4)
        self.task: asyncio.Task | None = None
        self.dispatch_tasks: set[asyncio.Task] = set()
        # Kept only as a reference for meter and status.  Its notes are never
        # played here: this path is intentionally direct Notochord output.
        self.asset: PortraitAsset | None = None
        self.current_emotion = "neutral"
        self.current_bpm = 96
        self.segment_index = 0
        self.notochord_event_count = 0
        self.notochord_track_counts: dict[str, int] = {}
        self.generation_error = ""
        self.phase = "stopped"

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def update_music_config(self, config: ActiveMusicConfig) -> None:
        self.config = config

    def add_emotion(self, emotion: EmotionState) -> None:
        if emotion.confidence >= .45:
            self.aggregator.add(emotion)

    def start(self) -> None:
        if self.running:
            return
        if self.model.active_provider != "notochord" or not self.model.loaded or self.model.model is None:
            raise ValueError("Noto Testing requires a loaded Notochord model")
        if not any(track.enabled and track.compute_enabled for track in self.config.tracks):
            raise ValueError("Noto Testing requires at least one enabled track")
        self.asset = None
        self.current_emotion = "neutral"
        self.segment_index = 0
        self.notochord_event_count = 0
        self.notochord_track_counts = {}
        self.generation_error = ""
        self.phase = "waiting_for_emotion"
        self.task = asyncio.create_task(self._run(), name="noto-testing-runtime")

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
        self.phase = "stopped"
        self.all_notes_off()

    def status(self) -> dict[str, Any]:
        profile = self.config.emotion_profiles.get(self.current_emotion)
        return {
            "running": self.running,
            "type": "noto_testing",
            "phase": self.phase,
            "initial_emotion_ready": self.asset is not None,
            "initial_asset_id": self.asset.id if self.asset else "",
            "initial_asset_title": self.asset.title if self.asset else "",
            "initial_asset_path": str(self.asset.path) if self.asset else "",
            "current_emotion": self.current_emotion,
            "profile_scale": profile.scale if profile else "",
            "profile_chord_quality": profile.chord_quality if profile else "",
            "current_bpm": self.current_bpm,
            "window_bars": self.WINDOW_BARS,
            "segment_index": self.segment_index,
            "notochord_event_count": self.notochord_event_count,
            "notochord_track_counts": self.notochord_track_counts,
            "model_detail": self.model.detail,
            "generation_error": self.generation_error,
        }

    async def _run(self) -> None:
        try:
            while self.aggregator.sample_count() < 4:
                await asyncio.sleep(.1)
            emotion = self.aggregator.aggregate()
            self.current_emotion = emotion.label
            self.asset = self.library.select(emotion.label, "loop")
            if self.asset is None:
                raise ValueError(f"no loop_machine asset for {emotion.label}")
            self.current_bpm = self.asset.bpm
            self.model.model.reset()
            self.segment_index = 1
            self.phase = "notochord_ensemble"

            while True:
                # Read emotion at the boundary, but do not let it veto the
                # model's melodic or harmonic choices.
                emotion = self.aggregator.aggregate()
                segment = self._compose_noto_segment(emotion)
                await self._play_segment(segment, "noto_testing_segment_started")
                self.segment_index += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.generation_error = f"Noto Testing stopped: {exc}"
            self.phase = "error"
            self.all_notes_off()
            await self.broadcast({"kind": "noto_testing_error", "noto_testing": self.status()})
            self.task = None

    def _compose_noto_segment(self, emotion: EmotionState) -> MusicSegment:
        profile = self.config.emotion_profiles[emotion.label]
        previous_emotion = self.current_emotion
        self.current_emotion = emotion.label
        self.current_bpm = round(profile.bpm_range[0] + (profile.bpm_range[1] - profile.bpm_range[0]) * emotion.arousal_norm)
        tracks = self._tracks()
        beats_per_bar = self.asset.beats_per_bar if self.asset else 4
        total_beats = self.WINDOW_BARS * beats_per_bar
        total_seconds = total_beats * 60 / self.current_bpm
        notes: list[SegmentNote] = []
        counts: dict[str, int] = {}
        # One global clock is the important change.  The old implementation
        # reserved only a handful of events per track, leaving long holes in
        # the phrase.  Here Notochord gets to keep writing until the full
        # four-bar window is occupied, while a deterministic role cycle keeps
        # bass, colour and pulse present alongside the lead line.
        cursor_seconds = 0.0
        role_cycle = self._sound_first_track_cycle(tracks)
        event_index = 0
        minimum = .025
        maximum = .5
        while cursor_seconds < total_seconds and event_index < self.MAX_EVENTS_PER_WINDOW:
            track = role_cycle[event_index % len(role_cycle)]
            allowed = self._sound_first_pitches(track)
            if not allowed:
                event_index += 1
                continue
            result = self.model.model.query(
                next_inst=self._instrument_for(track),
                include_pitch=allowed,
                min_time=minimum,
                max_time=maximum,
                min_vel=max(track.velocity_range[0], profile.velocity_range[0]),
                max_vel=min(track.velocity_range[1], profile.velocity_range[1]),
                pitch_temp=.78,
                velocity_temp=.65,
                rhythm_temp=.72,
                timing_temp=.35,
            )
            delay_seconds = max(minimum, min(maximum, float(result["time"])))
            cursor_seconds += delay_seconds
            if cursor_seconds >= total_seconds:
                break
            pitch = int(result["pitch"])
            velocity = max(track.velocity_range[0], min(track.velocity_range[1], int(result["vel"])))
            duration = self._duration_beats(track, total_beats - cursor_seconds * self.current_bpm / 60)
            notes.append(SegmentNote(
                beat=round(cursor_seconds * self.current_bpm / 60, 3), duration_beats=duration, pitch=pitch, velocity=velocity,
                track_id=track.id, channel=track.midi_channel,
                voice_role="theme" if track.role == "melody" else "harmony",
                generated_by="notochord",
            ))
            counts[track.id] = counts.get(track.id, 0) + 1
            self.model.model.feed(self._instrument_for(track), pitch, delay_seconds, velocity)
            event_index += 1

        self.notochord_track_counts = counts
        self.notochord_event_count += len(notes)
        return MusicSegment(
            id=uuid.uuid4().hex[:12], emotion=emotion.label, previous_emotion=previous_emotion,
            bpm=self.current_bpm, bars=self.WINDOW_BARS, beats_per_bar=beats_per_bar,
            root_note=self.config.global_settings.root_note, scale=profile.scale, source="model", form_section="variation",
            phrase_id=f"noto:{self.segment_index}", portrait=emotion.label,
            portrait_asset_id=self.asset.id if self.asset else "", portrait_asset_title=self.asset.title if self.asset else "",
            portrait_role="loop", notes=sorted(notes, key=lambda note: (note.beat, note.track_id, note.pitch)),
            notochord_modified_count=len(notes), notochord_track_counts=counts,
            bass_note_count=sum(track.role == "bass" for track in tracks for _ in range(counts.get(track.id, 0))),
            drum_note_count=sum(track.role == "drum" for track in tracks for _ in range(counts.get(track.id, 0))),
            cymbal_note_count=sum(track.role == "cymbal" for track in tracks for _ in range(counts.get(track.id, 0))),
        )

    def _tracks(self) -> list[TrackConfig]:
        return [track for track in self.config.tracks if track.enabled and track.compute_enabled]

    def _instrument_for(self, track: TrackConfig) -> int:
        configured = getattr(track, "notochord_instrument", None)
        if isinstance(configured, int):
            return configured
        if track.role in {"drum", "cymbal"}:
            return 129
        return (track.midi_program if track.midi_program is not None else 0) + 1

    def _sound_first_track_cycle(self, tracks: list[TrackConfig]) -> list[TrackConfig]:
        weights = {"melody": 4, "pad": 2, "chord": 2, "bass": 2, "drum": 2, "cymbal": 1}
        cycle = [track for track in tracks for _ in range(weights.get(track.role, 1))]
        return cycle or tracks

    @staticmethod
    def _duration_beats(track: TrackConfig, remaining_beats: float) -> float:
        role_floor = {"pad": 1.0, "bass": .5, "drum": .125, "cymbal": .125}.get(track.role, .25)
        requested = track.note_length_ms / 1000
        # Convert at a neutral 120 BPM then cap against the current phrase;
        # articulation stays recognisable without turning the texture into a
        # blanket of stuck notes.
        beats = max(role_floor, requested * 2)
        return round(min(beats, max(.125, remaining_beats)), 3)

    @staticmethod
    def _sound_first_pitches(track: TrackConfig) -> list[int]:
        """Leave pitch choice to the model; only protect physical track range."""
        if track.role in {"drum", "cymbal"}:
            legal = getattr(track, "drum_notes", {}) or {}
            return [int(pitch) for pitch in legal.values() if track.pitch_range[0] <= int(pitch) <= track.pitch_range[1]]
        return list(range(track.pitch_range[0], track.pitch_range[1] + 1))

    async def _play_segment(self, segment: MusicSegment, kind: str) -> None:
        await self.broadcast({"kind": kind, "segment": segment.model_dump(), "noto_testing": self.status()})
        tasks = self._schedule(segment)
        await asyncio.sleep(segment.duration_seconds)
        await asyncio.gather(*tasks, return_exceptions=True)
        self.dispatch_tasks.difference_update(tasks)

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
