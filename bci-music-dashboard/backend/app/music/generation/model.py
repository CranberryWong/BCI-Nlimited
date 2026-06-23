from __future__ import annotations

import json
from pathlib import Path
import time
import uuid

from app.music.scales import root_pc, scale_notes
from app.music.schemas import EmotionState, MusicSegment, SegmentNote, TrackConfig
from app.music.generation.voicing import chord_pitch_classes


EMOTION_SCALES = {
    "joy": ("gong", "zhi"),
    "calm": ("gong",),
    "neutral": ("gong", "shang"),
    "tense": ("jue",),
    "sad": ("yu",),
}


class MelodyModel:
    def __init__(
        self,
        checkpoint_path: Path,
        config_path: Path,
        provider: str = "auto",
        notochord_checkpoint: Path | None = None,
        notochord_device: str = "cpu",
        notochord_instrument: int = 14,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.config_path = config_path
        self.provider = provider
        self.notochord_checkpoint = notochord_checkpoint
        self.notochord_device = notochord_device
        self.notochord_instrument = notochord_instrument
        self.active_provider = "rule"
        self.model = None
        self.metadata: dict = {}
        self.detail = "model_missing"

    @property
    def available(self) -> bool:
        if self.provider == "rule":
            return False
        local_available = self.checkpoint_path.exists() and self.config_path.exists()
        notochord_available = bool(
            self.notochord_checkpoint and self.notochord_checkpoint.exists()
        )
        if self.provider == "local":
            return local_available
        if self.provider == "notochord":
            return notochord_available
        return notochord_available or local_available

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def load(self) -> bool:
        self.model = None
        self.active_provider = "rule"
        self.metadata = {}
        if self.provider == "rule":
            self.detail = "disabled:rule"
            return False

        errors: list[str] = []
        if self.provider in {"auto", "notochord"}:
            if self.notochord_checkpoint and self.notochord_checkpoint.exists():
                try:
                    self._load_notochord()
                    return True
                except Exception as exc:
                    errors.append(f"notochord: {exc}")
            elif self.provider == "notochord":
                errors.append("notochord checkpoint missing")

        if self.provider in {"auto", "local"}:
            if self.checkpoint_path.exists() and self.config_path.exists():
                try:
                    self._load_local_transformer()
                    return True
                except Exception as exc:
                    errors.append(f"local: {exc}")
            elif self.provider == "local":
                errors.append("local checkpoint or config missing")

        self.detail = "load_error: " + "; ".join(errors) if errors else "model_missing"
        return False

    def _load_notochord(self) -> None:
        import torch
        from notochord import Notochord

        model = Notochord.from_checkpoint(str(self.notochord_checkpoint))
        device = self.notochord_device
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        model.to(device)
        model.eval()
        model.reset()
        self.model = model
        self.active_provider = "notochord"
        self.metadata = {
            "provider": "notochord",
            "checkpoint": str(self.notochord_checkpoint),
            "device": device,
            "instrument": self.notochord_instrument,
        }
        self.detail = f"ready:notochord:{device}"

    def _load_local_transformer(self) -> None:
        import torch

        from app.music.generation.network import MelodyTransformer

        self.metadata = json.loads(self.config_path.read_text(encoding="utf-8"))
        model = MelodyTransformer.from_config(self.metadata)
        payload = torch.load(self.checkpoint_path, map_location="cpu", weights_only=True)
        model.load_state_dict(payload["model_state"] if "model_state" in payload else payload)
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model.to(device)
        model.eval()
        self.model = model
        self.active_provider = "local"
        self.metadata["provider"] = "local"
        self.metadata["device"] = device
        self.detail = f"ready:local:{device}"

    def generate_candidates(
        self,
        emotion: EmotionState,
        previous: MusicSegment | None,
        track: TrackConfig,
        bpm: int,
        count: int,
        bars: int,
        beats_per_bar: int,
    ) -> list[MusicSegment]:
        if self.model is None:
            return []
        if self.active_provider == "notochord":
            return self._generate_notochord(
                emotion, previous, track, bpm, count, bars, beats_per_bar
            )
        return self._generate_local(
            emotion, previous, track, bpm, count, bars, beats_per_bar
        )

    def ornament_segment(
        self,
        segment: MusicSegment,
        emotion: EmotionState,
        track: TrackConfig,
        freedom: float,
        immutable_beats: set[float],
    ) -> MusicSegment:
        if self.active_provider != "notochord" or self.model is None or freedom <= 0:
            return segment
        track_notes = [note for note in segment.notes if note.track_id == track.id]
        tagged_theme = [note for note in track_notes if note.voice_role == "theme"]
        melody = sorted(
            tagged_theme or [note for note in track_notes if note.voice_role is None],
            key=lambda note: note.beat,
        )
        if len(melody) < 2:
            return segment
        allowed = scale_notes(
            root_pc(segment.root_note),
            segment.scale,
            track.pitch_range[0],
            track.pitch_range[1],
        )
        seconds_per_beat = 60.0 / segment.bpm
        self.model.reset()
        ornaments: list[SegmentNote] = []
        replacements: dict[int, SegmentNote] = {}
        harmony_notes = [
            note for note in track_notes if note.voice_role == "harmony"
        ]
        revoice_rate = float(getattr(track, "notochord_revoice_rate", 0.25))
        max_revoices = min(
            len(harmony_notes),
            max(0, round(len(harmony_notes) * revoice_rate * freedom)),
        )
        for index, harmony_note in enumerate(harmony_notes):
            if len(replacements) >= max_revoices:
                break
            if harmony_note.beat in immutable_beats or index % 3 != 1:
                continue
            theme_note = next(
                (
                    note for note in melody
                    if abs(note.beat - harmony_note.beat) < 0.001
                ),
                None,
            )
            if theme_note is None:
                continue
            occupied = {
                note.pitch for note in track_notes
                if abs(note.beat - harmony_note.beat) < 0.001
            }
            bar = min(
                int(harmony_note.beat // segment.beats_per_bar),
                len(segment.harmony) - 1,
            )
            chord_tones = chord_pitch_classes(
                segment.root_note, segment.harmony[bar]
            )
            choices = [
                pitch for pitch in allowed
                if pitch < theme_note.pitch
                and abs(pitch - harmony_note.pitch) <= 5
                and pitch not in occupied
                and pitch % 12 in chord_tones
            ]
            if not choices:
                continue
            result = self.model.query(
                next_inst=self.notochord_instrument,
                next_time=max(0.0, harmony_note.beat * seconds_per_beat),
                include_pitch=choices,
                min_vel=max(track.velocity_range[0], harmony_note.velocity - 8),
                max_vel=min(track.velocity_range[1], harmony_note.velocity + 5),
                pitch_temp=0.72,
                velocity_temp=0.62,
            )
            pitch = int(self._number(result["pitch"]))
            velocity = int(self._number(result["vel"]))
            if pitch not in choices:
                continue
            replacements[id(harmony_note)] = harmony_note.model_copy(update={
                "pitch": pitch,
                "velocity": max(1, min(127, velocity)),
                "generated_by": "notochord",
            })

        arpeggio_notes = [
            note for note in track_notes
            if note.voice_role == "ornament" and note.generated_by == "rule"
        ]
        arpeggio_rate = float(getattr(track, "arpeggio_notochord_rate", 0.2))
        max_arpeggio_replacements = min(
            len(arpeggio_notes),
            max(0, round(len(arpeggio_notes) * arpeggio_rate * freedom)),
        )
        arpeggio_replacements = 0
        for index, ornament_note in enumerate(arpeggio_notes):
            if arpeggio_replacements >= max_arpeggio_replacements:
                break
            if index % 4 not in {1, 3}:
                continue
            if any(abs(ornament_note.beat - anchor) < 0.25 for anchor in immutable_beats):
                continue
            previous_theme = max(
                (note for note in melody if note.beat <= ornament_note.beat),
                key=lambda note: note.beat,
                default=None,
            )
            next_theme = min(
                (note for note in melody if note.beat >= ornament_note.beat),
                key=lambda note: note.beat,
                default=None,
            )
            reference = previous_theme or next_theme
            if reference is None:
                continue
            bar = min(
                int(ornament_note.beat // segment.beats_per_bar),
                len(segment.harmony) - 1,
            )
            chord_tones = chord_pitch_classes(
                segment.root_note, segment.harmony[bar]
            )
            occupied = {
                note.pitch for note in track_notes
                if abs(note.beat - ornament_note.beat) < 0.001
            }
            choices = [
                pitch for pitch in allowed
                if pitch < reference.pitch
                and abs(pitch - ornament_note.pitch) <= 5
                and pitch not in occupied
                and pitch % 12 in chord_tones
            ]
            if not choices:
                continue
            result = self.model.query(
                next_inst=self.notochord_instrument,
                next_time=max(0.0, ornament_note.beat * seconds_per_beat),
                include_pitch=choices,
                min_vel=max(track.velocity_range[0], ornament_note.velocity - 8),
                max_vel=min(track.velocity_range[1], ornament_note.velocity + 5),
                pitch_temp=0.76,
                velocity_temp=0.62,
            )
            pitch = int(self._number(result["pitch"]))
            velocity = int(self._number(result["vel"]))
            if pitch not in choices:
                continue
            replacements[id(ornament_note)] = ornament_note.model_copy(update={
                "pitch": pitch,
                "velocity": max(1, min(127, velocity)),
                "generated_by": "notochord",
            })
            arpeggio_replacements += 1

        max_ornaments = max(1, round(segment.bars * freedom))
        for left, right in zip(melody, melody[1:]):
            self.model.feed(
                self.notochord_instrument,
                left.pitch,
                max(0.0, left.beat * seconds_per_beat if not ornaments else 0.0),
                left.velocity,
            )
            self.model.feed(
                self.notochord_instrument,
                left.pitch,
                left.duration_beats * seconds_per_beat,
                0,
            )
            gap_start = left.beat + left.duration_beats
            gap = right.beat - gap_start
            if gap < 0.5 or len(ornaments) >= max_ornaments:
                continue
            remaining = max_ornaments - len(ornaments)
            answer_count = 1 if gap < 1.5 else min(4, remaining, max(1, int(gap / 0.5) - 1))
            answer_span = min(gap, segment.beats_per_bar * 2)
            previous_pitch = left.pitch
            previous_beat = gap_start
            for answer_index in range(answer_count):
                beat = round(
                    gap_start + answer_span * (answer_index + 1) / (answer_count + 1),
                    3,
                )
                if any(abs(beat - anchor) < 0.25 for anchor in immutable_beats):
                    continue
                choices = [
                    pitch for pitch in allowed
                    if abs(pitch - previous_pitch) <= 5
                    and abs(right.pitch - pitch) <= 7
                    and pitch not in {previous_pitch, right.pitch}
                ]
                if not choices:
                    continue
                result = self.model.query(
                    next_inst=self.notochord_instrument,
                    next_time=(beat - previous_beat) * seconds_per_beat,
                    include_pitch=choices,
                    min_vel=max(track.velocity_range[0], left.velocity - 22),
                    max_vel=min(track.velocity_range[1], left.velocity - 5),
                    pitch_temp=0.82,
                    velocity_temp=0.7,
                )
                pitch = int(self._number(result["pitch"]))
                velocity = int(self._number(result["vel"]))
                if pitch not in choices:
                    continue
                spacing = answer_span / (answer_count + 1)
                duration = min(0.4, max(0.2, spacing * 0.72))
                ornaments.append(SegmentNote(
                    beat=beat,
                    duration_beats=duration,
                    pitch=pitch,
                    velocity=max(1, min(127, velocity)),
                    track_id=track.id,
                    channel=track.midi_channel,
                    voice_role="ornament",
                    generated_by="notochord",
                ))
                self.model.feed(
                    self.notochord_instrument,
                    pitch,
                    (beat - previous_beat) * seconds_per_beat,
                    velocity,
                )
                self.model.feed(
                    self.notochord_instrument,
                    pitch,
                    duration * seconds_per_beat,
                    0,
                )
                previous_pitch = pitch
                previous_beat = beat
        if not ornaments and not replacements:
            return segment
        updated_notes = [
            replacements.get(id(note), note) for note in segment.notes
        ] + ornaments
        modified_count = len(replacements) + len(ornaments)
        return segment.model_copy(update={
            "source": "hybrid",
            "ornamented_beats": [note.beat for note in ornaments],
            "notochord_modified_count": modified_count,
            "arpeggio_note_count": sum(note.voice_role == "ornament" for note in updated_notes),
            "notes": sorted(updated_notes, key=lambda note: (note.beat, note.track_id, note.pitch)),
        })

    def _generate_notochord(
        self,
        emotion: EmotionState,
        previous: MusicSegment | None,
        track: TrackConfig,
        bpm: int,
        count: int,
        bars: int,
        beats_per_bar: int,
    ) -> list[MusicSegment]:
        started = time.perf_counter()
        candidates: list[MusicSegment] = []
        scales = EMOTION_SCALES[emotion.label]
        root_note = track.root_note if track.root_note != "auto" else "C"
        total_beats = bars * beats_per_bar
        step = 0.5 if emotion.arousal_norm >= 0.62 else 1.0
        if emotion.label in {"calm", "sad"}:
            step = 1.0
        duration_beats = step * (0.82 if emotion.label in {"calm", "sad"} else 0.72)
        seconds_per_beat = 60.0 / bpm
        velocity_center = round(
            track.velocity_range[0]
            + (track.velocity_range[1] - track.velocity_range[0])
            * (0.3 + emotion.arousal_norm * 0.45)
        )

        for index in range(count):
            scale = scales[index % len(scales)]
            allowed = self._notochord_register(track, emotion, root_note, scale)
            if not allowed:
                continue
            self.model.reset()
            self._feed_previous(previous, track.id, seconds_per_beat)
            previous_pitch = self._previous_pitch(previous, track.id)
            notes: list[SegmentNote] = []
            beat = 0.0
            gap_seconds = 0.0
            while beat < total_beats:
                choices = [
                    pitch for pitch in allowed
                    if previous_pitch is None or abs(pitch - previous_pitch) <= 7
                ] or allowed
                phrase_index = round(beat / step)
                if (
                    previous_pitch is not None
                    and phrase_index % 4 in {1, 2, 3}
                    and any(pitch != previous_pitch for pitch in choices)
                ):
                    choices = [pitch for pitch in choices if pitch != previous_pitch]
                if beat == 0 and previous_pitch is not None:
                    close = [pitch for pitch in choices if abs(pitch - previous_pitch) <= 7]
                    choices = close or choices
                result = self.model.query(
                    next_inst=self.notochord_instrument,
                    next_time=gap_seconds,
                    include_pitch=choices,
                    min_vel=max(1, velocity_center - 16),
                    max_vel=min(127, velocity_center + 16),
                    index_pitch=(index + phrase_index) % min(3, len(choices)),
                    velocity_temp=0.7,
                )
                pitch = int(self._number(result["pitch"]))
                velocity = int(self._number(result["vel"]))
                self.model.feed(
                    self.notochord_instrument, pitch, gap_seconds, velocity
                )
                note_duration = min(duration_beats, total_beats - beat)
                self.model.feed(
                    self.notochord_instrument,
                    pitch,
                    note_duration * seconds_per_beat,
                    0,
                )
                notes.append(SegmentNote(
                    beat=beat,
                    duration_beats=max(0.25, note_duration),
                    pitch=pitch,
                    velocity=max(1, min(127, velocity)),
                    track_id=track.id,
                    channel=track.midi_channel,
                ))
                previous_pitch = pitch
                gap_seconds = max(0.0, (step - note_duration) * seconds_per_beat)
                beat += step

            if notes:
                candidates.append(MusicSegment(
                    id=uuid.uuid4().hex[:12],
                    emotion=emotion.label,
                    previous_emotion=previous.emotion if previous else "neutral",
                    bpm=bpm,
                    bars=bars,
                    beats_per_bar=beats_per_bar,
                    root_note=root_note,
                    scale=scale,
                    source="model",
                    generation_ms=(time.perf_counter() - started) * 1000,
                    notes=notes,
                ))
        return candidates

    @staticmethod
    def _notochord_register(
        track: TrackConfig,
        emotion: EmotionState,
        root_note: str,
        scale: str,
    ) -> list[int]:
        low, high = track.pitch_range
        register_width = min(16, high - low)
        register_low = round(low + (high - low - register_width) * emotion.valence_norm)
        register_high = register_low + register_width
        return scale_notes(root_pc(root_note), scale, register_low, register_high)

    def _feed_previous(
        self,
        previous: MusicSegment | None,
        track_id: str,
        seconds_per_beat: float,
    ) -> None:
        if previous is None:
            return
        melody = sorted(
            [note for note in previous.notes if note.track_id == track_id],
            key=lambda note: note.beat,
        )
        if not melody:
            return
        start_beat = max(0.0, previous.total_beats - previous.beats_per_bar)
        cursor = start_beat
        for note in melody:
            if note.beat < start_beat:
                continue
            onset_delta = max(0.0, note.beat - cursor) * seconds_per_beat
            self.model.feed(
                self.notochord_instrument, note.pitch, onset_delta, note.velocity
            )
            self.model.feed(
                self.notochord_instrument,
                note.pitch,
                note.duration_beats * seconds_per_beat,
                0,
            )
            cursor = note.beat + note.duration_beats

    @staticmethod
    def _previous_pitch(previous: MusicSegment | None, track_id: str) -> int | None:
        if previous is None:
            return None
        notes = [note.pitch for note in previous.notes if note.track_id == track_id]
        return notes[-1] if notes else None

    @staticmethod
    def _number(value):
        return value.item() if hasattr(value, "item") else value

    def _generate_local(
        self,
        emotion: EmotionState,
        previous: MusicSegment | None,
        track: TrackConfig,
        bpm: int,
        count: int,
        bars: int,
        beats_per_bar: int,
    ) -> list[MusicSegment]:
        import torch

        from app.music.generation.tokens import decode_tokens, prompt_tokens

        started = time.perf_counter()
        device = next(self.model.parameters()).device
        prompt = prompt_tokens(emotion.label, previous.emotion if previous else "neutral", bpm)
        candidates: list[MusicSegment] = []
        for _ in range(count):
            tokens = self.model.sample(
                torch.tensor([prompt], dtype=torch.long, device=device),
                max_new_tokens=384,
                temperature=0.9,
                top_k=32,
            )[0].tolist()
            notes = decode_tokens(tokens[len(prompt):], track.id, track.midi_channel, bars, beats_per_bar)
            if notes:
                candidates.append(MusicSegment(
                    id=uuid.uuid4().hex[:12],
                    emotion=emotion.label,
                    previous_emotion=previous.emotion if previous else "neutral",
                    bpm=bpm,
                    bars=bars,
                    beats_per_bar=beats_per_bar,
                    root_note=track.root_note if track.root_note != "auto" else "C",
                    scale=self.metadata.get("emotion_scales", {}).get(emotion.label, "gong"),
                    source="model",
                    generation_ms=(time.perf_counter() - started) * 1000,
                    notes=notes,
                ))
        return candidates

    def public_metadata(self) -> dict:
        return {
            "provider": self.active_provider,
            "requested_provider": self.provider,
            "checkpoint": (
                str(self.notochord_checkpoint)
                if self.active_provider == "notochord"
                else str(self.checkpoint_path)
            ),
            "config": str(self.config_path),
            "available": self.available,
            "loaded": self.loaded,
            "detail": self.detail,
            "metadata": self.metadata,
        }
