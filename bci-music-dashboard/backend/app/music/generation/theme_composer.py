from __future__ import annotations

import random
import time
import uuid

from app.music.generation.form import FormPosition
from app.music.generation.theme_library import Theme, ThemeNote
from app.music.generation.voicing import MelodyArpeggioEngine, MelodyVoicingEngine
from app.music.scales import ROOTS, SCALES
from app.music.schemas import EmotionState, MusicSegment, SegmentNote, TrackConfig


ROMAN_DEGREES = {
    "I": (0, "major"),
    "ii": (2, "minor"),
    "iii": (4, "minor"),
    "IV": (5, "major"),
    "V": (7, "major"),
    "V7": (7, "dominant"),
    "vi": (9, "minor"),
    "VII": (11, "diminished"),
}

SECTION_THEME_DENSITY = {
    "intro": 0.35,
    "theme": 1.0,
    "variation": 0.76,
    "development": 0.48,
    "climax": 0.72,
    "return": 1.0,
    "coda": 0.62,
}


class ThemeComposer:
    def __init__(self) -> None:
        self.voicing = MelodyVoicingEngine()
        self.arpeggio = MelodyArpeggioEngine()

    def compose(
        self,
        theme: Theme,
        position: FormPosition,
        emotion: EmotionState,
        previous_emotion: str,
        bpm: int,
        tracks: list[TrackConfig],
        recognition: float,
        freedom: float,
    ) -> MusicSegment:
        started = time.perf_counter()
        melody_track = self._required_track(tracks, "melody")
        harmony = list(theme.harmony)
        melody = self._melody(
            theme, position, emotion, melody_track, recognition, freedom
        )
        voiced_melody = self.voicing.apply(
            melody,
            harmony,
            theme.home_key,
            theme.beats_per_bar,
            position.section,
            emotion,
            melody_track,
            set(theme.immutable_beats),
        )
        arpeggiated_melody = self.arpeggio.apply(
            melody,
            voiced_melody,
            harmony,
            theme.home_key,
            theme.mode,
            theme.beats_per_bar,
            position.section,
            emotion,
            melody_track,
            set(theme.immutable_beats),
        )
        notes = list(arpeggiated_melody)
        pad = self._optional_track(tracks, "pad") or self._optional_track(tracks, "chord")
        if pad:
            notes.extend(self._pad(theme, harmony, emotion, position, pad))
        bass = self._optional_track(tracks, "bass")
        if bass:
            notes.extend(self._bass(theme, harmony, emotion, position, bass))
        drum = self._optional_track(tracks, "drum")
        if drum:
            notes.extend(self._drums(theme, emotion, position, drum))
        cymbal = self._optional_track(tracks, "cymbal")
        if cymbal:
            notes.extend(self._cymbals(theme, emotion, position, cymbal))

        transition = self._transition(position, emotion.label, previous_emotion)
        actual_max_voices, harmony_note_count = self.voicing.metrics(arpeggiated_melody)
        arpeggio_note_count = self.arpeggio.count(arpeggiated_melody)
        return MusicSegment(
            id=uuid.uuid4().hex[:12],
            emotion=emotion.label,
            previous_emotion=previous_emotion,
            bpm=bpm,
            bars=theme.bars,
            beats_per_bar=theme.beats_per_bar,
            root_note=theme.home_key,
            scale=theme.mode,
            source="theme",
            form_section=position.section,
            phrase_id=position.phrase_id,
            theme_id=theme.id,
            theme_similarity=self._similarity(theme, melody),
            harmony=harmony,
            transition_type=transition,
            actual_max_voices=actual_max_voices,
            harmony_note_count=harmony_note_count,
            arpeggio_note_count=arpeggio_note_count,
            generation_ms=(time.perf_counter() - started) * 1000,
            notes=sorted(notes, key=lambda note: (note.beat, note.track_id, note.pitch)),
        )

    def _melody(
        self,
        theme: Theme,
        position: FormPosition,
        emotion: EmotionState,
        track: TrackConfig,
        recognition: float,
        freedom: float,
    ) -> list[SegmentNote]:
        density = SECTION_THEME_DENSITY[position.section]
        density = max(density, recognition * 0.7)
        variant = theme.emotion_variants.get(emotion.label, {})
        octave = int(variant.get("octave_shift", 0))
        if position.section == "climax":
            octave += 12
        elif position.section == "coda" and emotion.label in {"sad", "calm"}:
            octave -= 12
        octave = max(-12, min(12, octave))
        velocity_gain = float(variant.get("velocity_gain", 1.0))
        rhythmic_activity = float(variant.get("rhythmic_activity", 0.6))
        notes: list[SegmentNote] = []

        for source in theme.notes:
            anchored = source.beat in theme.immutable_beats
            if not anchored:
                keep_probability = density * (0.82 + rhythmic_activity * 0.18)
                if random.random() > keep_probability:
                    continue
            pitch = self._fit_pitch(source.pitch + octave, track.pitch_range)
            articulation = 0.9 if source.duration_beats > 1.0 else 0.82
            duration = source.duration_beats * articulation
            if position.section == "intro":
                duration *= 1.08
            elif position.section == "variation" and emotion.arousal_norm > 0.62 and not anchored:
                duration = max(0.25, duration * 0.7)
            elif emotion.label in {"calm", "sad"}:
                duration *= 1.06
            duration = min(duration, theme.bars * theme.beats_per_bar - source.beat)
            velocity = round(
                source.velocity
                * velocity_gain
                * (0.72 + emotion.arousal_norm * 0.42)
            )
            if position.section == "intro":
                velocity = round(velocity * 0.75)
            elif position.section == "climax":
                velocity = round(velocity * 1.12)
            notes.append(SegmentNote(
                beat=source.beat,
                duration_beats=max(0.2, duration),
                pitch=pitch,
                velocity=max(track.velocity_range[0], min(track.velocity_range[1], velocity)),
                track_id=track.id,
                channel=track.midi_channel,
                voice_role="theme",
                generated_by="theme",
            ))

        if position.section in {"variation", "development"} and freedom > 0.15:
            notes = self._vary_mutable_notes(notes, theme, track, freedom)
        return sorted(notes, key=lambda note: note.beat)

    def _vary_mutable_notes(
        self,
        notes: list[SegmentNote],
        theme: Theme,
        track: TrackConfig,
        freedom: float,
    ) -> list[SegmentNote]:
        scale = SCALES.get(theme.mode, SCALES["major"])
        root = ROOTS.get(theme.home_key, 0)
        allowed = [
            pitch for pitch in range(track.pitch_range[0], track.pitch_range[1] + 1)
            if (pitch - root) % 12 in scale
        ]
        result: list[SegmentNote] = []
        for note in notes:
            if note.beat in theme.immutable_beats or random.random() > freedom * 0.45:
                result.append(note)
                continue
            direction = random.choice((-2, 2))
            pitch = min(allowed, key=lambda candidate: abs(candidate - (note.pitch + direction)))
            result.append(note.model_copy(update={"pitch": pitch}))
        return result

    def _pad(
        self,
        theme: Theme,
        harmony: list[str],
        emotion: EmotionState,
        position: FormPosition,
        track: TrackConfig,
    ) -> list[SegmentNote]:
        result: list[SegmentNote] = []
        for bar, symbol in enumerate(harmony):
            root, intervals = self._chord(theme, symbol)
            pitches = [
                self._fit_pitch(root + interval, track.pitch_range)
                for interval in intervals
            ]
            velocity = round(
                track.velocity_range[0]
                + (track.velocity_range[1] - track.velocity_range[0])
                * (0.2 + emotion.arousal_norm * 0.22)
            )
            if position.section == "climax":
                velocity = min(track.velocity_range[1], velocity + 10)
            for pitch in sorted(set(pitches)):
                result.append(SegmentNote(
                    beat=bar * theme.beats_per_bar,
                    duration_beats=theme.beats_per_bar * 0.96,
                    pitch=pitch,
                    velocity=velocity,
                    track_id=track.id,
                    channel=track.midi_channel,
                ))
        return result

    def _bass(
        self,
        theme: Theme,
        harmony: list[str],
        emotion: EmotionState,
        position: FormPosition,
        track: TrackConfig,
    ) -> list[SegmentNote]:
        result: list[SegmentNote] = []
        for bar, symbol in enumerate(harmony):
            root, _ = self._chord(theme, symbol)
            pitch = self._fit_pitch(root, track.pitch_range)
            velocity = round(
                track.velocity_range[0]
                + (track.velocity_range[1] - track.velocity_range[0])
                * (0.28 + emotion.arousal_norm * 0.35)
            )
            result.append(SegmentNote(
                beat=bar * theme.beats_per_bar,
                duration_beats=theme.beats_per_bar * 0.88,
                pitch=pitch,
                velocity=velocity,
                track_id=track.id,
                channel=track.midi_channel,
            ))
            if position.section in {"development", "climax"} and emotion.arousal_norm > 0.6:
                fifth = self._fit_pitch(root + 7, track.pitch_range)
                result.append(SegmentNote(
                    beat=bar * theme.beats_per_bar + 2,
                    duration_beats=1.7,
                    pitch=fifth,
                    velocity=max(track.velocity_range[0], velocity - 8),
                    track_id=track.id,
                    channel=track.midi_channel,
                ))
        return result

    def _drums(
        self,
        theme: Theme,
        emotion: EmotionState,
        position: FormPosition,
        track: TrackConfig,
    ) -> list[SegmentNote]:
        if position.section == "intro" and emotion.arousal_norm < 0.55:
            return []
        drum_notes = getattr(track, "drum_notes", {}) or {}
        result: list[SegmentNote] = []
        activity = emotion.arousal_norm + (0.2 if position.section == "climax" else 0)
        for bar in range(theme.bars):
            hits = [(0.0, drum_notes.get("kick", 36))]
            if activity >= 0.45:
                hits.append((2.0, drum_notes.get("kick", 36)))
            if activity >= 0.62 and position.section not in {"intro", "coda"}:
                hits.extend([
                    (1.0, drum_notes.get("snare", 38)),
                    (3.0, drum_notes.get("snare", 38)),
                ])
            for local_beat, pitch in hits:
                result.append(SegmentNote(
                    beat=bar * theme.beats_per_bar + local_beat,
                    duration_beats=0.18,
                    pitch=pitch,
                    velocity=round(48 + min(1.0, activity) * 48),
                    track_id=track.id,
                    channel=track.midi_channel,
                ))
        return result

    def _cymbals(
        self,
        theme: Theme,
        emotion: EmotionState,
        position: FormPosition,
        track: TrackConfig,
    ) -> list[SegmentNote]:
        notes: list[SegmentNote] = []
        if position.section_changed or position.section == "climax":
            notes.append(SegmentNote(
                beat=0,
                duration_beats=0.35,
                pitch=49,
                velocity=round(58 + emotion.arousal_norm * 42),
                track_id=track.id,
                channel=track.midi_channel,
            ))
        if position.section in {"development", "climax"} and emotion.arousal_norm >= 0.68:
            for bar in range(theme.bars):
                notes.append(SegmentNote(
                    beat=bar * theme.beats_per_bar + 3.5,
                    duration_beats=0.12,
                    pitch=42,
                    velocity=round(40 + emotion.arousal_norm * 35),
                    track_id=track.id,
                    channel=track.midi_channel,
                ))
        return notes

    @staticmethod
    def _chord(theme: Theme, symbol: str) -> tuple[int, tuple[int, ...]]:
        degree, quality = ROMAN_DEGREES.get(symbol, ROMAN_DEGREES["I"])
        root = 48 + ROOTS.get(theme.home_key, 0) + degree
        intervals = {
            "major": (0, 4, 7),
            "minor": (0, 3, 7),
            "dominant": (0, 4, 7, 10),
            "diminished": (0, 3, 6),
        }[quality]
        return root, intervals

    @staticmethod
    def _fit_pitch(pitch: int, pitch_range: tuple[int, int]) -> int:
        low, high = pitch_range
        while pitch < low:
            pitch += 12
        while pitch > high:
            pitch -= 12
        return max(low, min(high, pitch))

    @staticmethod
    def _required_track(tracks: list[TrackConfig], role: str) -> TrackConfig:
        track = ThemeComposer._optional_track(tracks, role)
        if not track:
            raise ValueError(f"enabled {role} track is required")
        return track

    @staticmethod
    def _optional_track(tracks: list[TrackConfig], role: str) -> TrackConfig | None:
        return next(
            (track for track in tracks if track.enabled and track.compute_enabled and track.role == role),
            None,
        )

    @staticmethod
    def _similarity(theme: Theme, melody: list[SegmentNote]) -> float:
        if not theme.notes:
            return 0.0
        by_beat = {
            round(note.beat, 3): note.pitch
            for note in melody
            if note.voice_role in {None, "theme"}
        }
        matched = sum(
            by_beat.get(round(note.beat, 3)) is not None
            and abs(by_beat[round(note.beat, 3)] - note.pitch) % 12 == 0
            for note in theme.notes
        )
        return round(matched / len(theme.notes), 3)

    @staticmethod
    def _transition(position: FormPosition, emotion: str, previous_emotion: str) -> str:
        if position.section == "coda":
            return "final"
        if position.section_changed:
            return "section_boundary"
        if emotion != previous_emotion:
            return "emotion_pivot"
        return "continue"
