from __future__ import annotations

from collections import defaultdict

from app.music.scales import ROOTS, SCALES
from app.music.schemas import EmotionState, SegmentNote, TrackConfig


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

QUALITY_INTERVALS = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "dominant": (0, 4, 7, 10),
    "diminished": (0, 3, 6),
}

SECTION_DENSITY = {
    "intro": 0.35,
    "theme": 1.0,
    "variation": 0.85,
    "development": 0.75,
    "climax": 1.0,
    "return": 1.0,
    "coda": 0.45,
}


def chord_pitch_classes(home_key: str, symbol: str) -> set[int]:
    degree, quality = ROMAN_DEGREES.get(symbol, ROMAN_DEGREES["I"])
    root_pc = (ROOTS.get(home_key, 0) + degree) % 12
    return {
        (root_pc + interval) % 12 for interval in QUALITY_INTERVALS[quality]
    }


class MelodyVoicingEngine:
    def apply(
        self,
        melody: list[SegmentNote],
        harmony: list[str],
        home_key: str,
        beats_per_bar: int,
        form_section: str,
        emotion: EmotionState,
        track: TrackConfig,
        immutable_beats: set[float],
    ) -> list[SegmentNote]:
        if (
            not bool(getattr(track, "voicing_enabled", True))
            or track.polyphony <= 1
            or not melody
        ):
            return melody

        density = float(getattr(track, "voicing_density", 0.55))
        density *= SECTION_DENSITY.get(form_section, 0.7)
        density *= 0.75 + emotion.arousal_norm * 0.4
        previous_voices: list[int] = []
        additions: list[SegmentNote] = []

        for index, theme_note in enumerate(melody):
            local_beat = theme_note.beat % beats_per_bar
            anchored = theme_note.beat in immutable_beats
            long_or_cadential = theme_note.duration_beats >= 1.25 or self._is_cadential(
                theme_note, melody, beats_per_bar
            )
            eligible = local_beat in {0, 2} or anchored or long_or_cadential
            if not eligible or not self._density_gate(index, density, anchored):
                continue

            voice_count = 2
            if track.polyphony >= 3 and (
                form_section == "climax" or long_or_cadential
            ):
                voice_count = 3
            voice_count = min(track.polyphony, voice_count)
            symbol = harmony[min(int(theme_note.beat // beats_per_bar), len(harmony) - 1)]
            candidates = self._chord_tones_below(
                theme_note.pitch, home_key, symbol, track.pitch_range
            )
            selected = self._select_smooth(candidates, previous_voices, voice_count - 1)
            previous_voices = selected
            for voice_index, pitch in enumerate(selected):
                duration_ratio = 0.9 - voice_index * 0.08
                velocity_drop = 16 + voice_index * 7
                additions.append(SegmentNote(
                    beat=theme_note.beat,
                    duration_beats=max(0.18, theme_note.duration_beats * duration_ratio),
                    pitch=pitch,
                    velocity=max(track.velocity_range[0], theme_note.velocity - velocity_drop),
                    track_id=track.id,
                    channel=track.midi_channel,
                    voice_role="harmony",
                    generated_by="rule",
                ))
        return sorted(melody + additions, key=lambda note: (note.beat, note.pitch))

    @staticmethod
    def metrics(notes: list[SegmentNote]) -> tuple[int, int]:
        melody_notes = [
            note for note in notes
            if note.voice_role in {"theme", "harmony", "ornament"}
        ]
        by_beat: dict[float, set[int]] = defaultdict(set)
        for note in melody_notes:
            by_beat[round(note.beat, 3)].add(note.pitch)
        maximum = max((len(pitches) for pitches in by_beat.values()), default=1)
        harmony_count = sum(note.voice_role == "harmony" for note in melody_notes)
        return maximum, harmony_count

    @staticmethod
    def _density_gate(index: int, density: float, anchored: bool) -> bool:
        if anchored:
            return True
        threshold = max(0, min(100, round(density * 100)))
        return (index * 37 + 17) % 100 < threshold

    @staticmethod
    def _is_cadential(
        note: SegmentNote,
        melody: list[SegmentNote],
        beats_per_bar: int,
    ) -> bool:
        if note is melody[-1]:
            return True
        return note.beat % (beats_per_bar * 4) >= beats_per_bar * 4 - 2

    @staticmethod
    def _chord_tones_below(
        melody_pitch: int,
        home_key: str,
        symbol: str,
        pitch_range: tuple[int, int],
    ) -> list[int]:
        pitch_classes = chord_pitch_classes(home_key, symbol)
        low, high = pitch_range
        candidates = [
            pitch for pitch in range(low, min(high, melody_pitch - 1) + 1)
            if pitch % 12 in pitch_classes and melody_pitch - pitch <= 12
        ]
        return sorted(candidates, reverse=True)

    @staticmethod
    def _select_smooth(
        candidates: list[int],
        previous: list[int],
        count: int,
    ) -> list[int]:
        selected: list[int] = []
        remaining = list(candidates)
        for voice_index in range(count):
            if not remaining:
                break
            target = previous[voice_index] if voice_index < len(previous) else remaining[0]
            close = [pitch for pitch in remaining if abs(pitch - target) <= 7]
            pitch = min(close or remaining, key=lambda item: (abs(item - target), -item))
            selected.append(pitch)
            remaining.remove(pitch)
        return sorted(selected, reverse=True)


class MelodyArpeggioEngine:
    def apply(
        self,
        melody_notes: list[SegmentNote],
        current_notes: list[SegmentNote],
        harmony: list[str],
        home_key: str,
        mode: str,
        beats_per_bar: int,
        form_section: str,
        emotion: EmotionState,
        track: TrackConfig,
        immutable_beats: set[float],
    ) -> list[SegmentNote]:
        if (
            not bool(getattr(track, "arpeggio_enabled", True))
            or track.polyphony <= 1
            or not melody_notes
        ):
            return current_notes

        rate = 0.25 if getattr(track, "arpeggio_rate", "1/8") == "1/16" else 0.5
        density = float(getattr(track, "arpeggio_density", 0.45))
        density *= {
            "intro": 0.35,
            "theme": 0.65,
            "variation": 1.0,
            "development": 1.1,
            "climax": 1.35,
            "return": 0.72,
            "coda": 0.42,
        }.get(form_section, 0.75)
        density *= 0.75 + emotion.arousal_norm * 0.45
        if emotion.label == "tense":
            density *= 0.82
        max_group = max(2, min(5, int(getattr(track, "arpeggio_max_group_notes", 5))))
        additions: list[SegmentNote] = []
        occupied = {
            (round(note.beat, 3), note.pitch)
            for note in current_notes
        }
        theme_by_beat = {
            round(note.beat, 3): note
            for note in melody_notes
        }

        for index, note in enumerate(melody_notes):
            group_start = self._group_start(note, melody_notes, index, beats_per_bar)
            group_end = min(
                note.beat + max(note.duration_beats, rate),
                note.beat + beats_per_bar,
            )
            next_note = melody_notes[index + 1] if index + 1 < len(melody_notes) else None
            if next_note:
                group_end = min(group_end, next_note.beat - 0.05)
            if group_end - group_start < rate:
                continue
            bar = min(int(note.beat // beats_per_bar), len(harmony) - 1)
            if not self._density_gate(index, bar, density, form_section, note.duration_beats):
                continue
            pitches = self._arpeggio_pitches(
                note.pitch,
                home_key,
                mode,
                harmony[bar],
                track.pitch_range,
            )
            if not pitches:
                continue
            beats = self._group_beats(group_start, group_end, rate, max_group, immutable_beats)
            if not beats:
                continue
            direction = -1 if (index + bar) % 2 == 0 else 1
            ordered = pitches if direction < 0 else list(reversed(pitches))
            for step_index, beat in enumerate(beats):
                if round(beat, 3) in theme_by_beat:
                    continue
                pitch = ordered[step_index % len(ordered)]
                if (round(beat, 3), pitch) in occupied:
                    continue
                nearest_theme = note if next_note is None else min(
                    (note, next_note), key=lambda item: abs(item.beat - beat)
                )
                if pitch >= nearest_theme.pitch:
                    continue
                duration = min(0.42, max(0.2, rate * 0.78))
                additions.append(SegmentNote(
                    beat=round(beat, 3),
                    duration_beats=duration,
                    pitch=pitch,
                    velocity=max(track.velocity_range[0], nearest_theme.velocity - 24),
                    track_id=track.id,
                    channel=track.midi_channel,
                    voice_role="ornament",
                    generated_by="rule",
                ))
                occupied.add((round(beat, 3), pitch))

        return sorted(current_notes + additions, key=lambda note: (note.beat, note.pitch))

    @staticmethod
    def count(notes: list[SegmentNote]) -> int:
        return sum(note.voice_role == "ornament" for note in notes)

    @staticmethod
    def _group_start(
        note: SegmentNote,
        melody: list[SegmentNote],
        index: int,
        beats_per_bar: int,
    ) -> float:
        local = note.beat % beats_per_bar
        if note.duration_beats >= 1.0:
            return note.beat + 0.5
        if local in {0, 2}:
            return note.beat + 0.5
        if index > 0:
            previous = melody[index - 1]
            gap_start = previous.beat + previous.duration_beats
            if note.beat - gap_start >= 0.5:
                return gap_start
        return note.beat + note.duration_beats

    @staticmethod
    def _group_beats(
        start: float,
        end: float,
        rate: float,
        max_group: int,
        immutable_beats: set[float],
    ) -> list[float]:
        beats: list[float] = []
        beat = start
        while beat < end - 0.05 and len(beats) < max_group:
            rounded = round(beat, 3)
            if not any(abs(rounded - anchor) < 0.25 for anchor in immutable_beats):
                beats.append(rounded)
            beat += rate
        return beats

    @staticmethod
    def _density_gate(
        index: int,
        bar: int,
        density: float,
        form_section: str,
        duration_beats: float,
    ) -> bool:
        if form_section == "climax" and duration_beats >= 0.5:
            return True
        threshold = max(0, min(100, round(density * 100)))
        return ((index + 1) * 29 + bar * 13) % 100 < threshold

    @staticmethod
    def _arpeggio_pitches(
        melody_pitch: int,
        home_key: str,
        mode: str,
        symbol: str,
        pitch_range: tuple[int, int],
    ) -> list[int]:
        chord_tones = chord_pitch_classes(home_key, symbol)
        root = ROOTS.get(home_key, 0)
        scale = SCALES.get(mode, SCALES.get("major", {0, 2, 4, 5, 7, 9, 11}))
        low, high = pitch_range
        candidates = [
            pitch for pitch in range(low, min(high, melody_pitch - 1) + 1)
            if melody_pitch - pitch <= 14
            and (
                pitch % 12 in chord_tones
                or (pitch - root) % 12 in scale
            )
        ]
        chord_first = [
            pitch for pitch in candidates
            if pitch % 12 in chord_tones
        ]
        passing = [
            pitch for pitch in candidates
            if pitch not in chord_first
        ]
        return sorted(chord_first[-4:] + passing[-2:], reverse=True)
