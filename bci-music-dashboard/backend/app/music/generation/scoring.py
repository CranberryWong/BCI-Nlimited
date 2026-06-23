from __future__ import annotations

from app.music.scales import root_pc, scale_notes
from app.music.schemas import MusicSegment
from app.music.generation.voicing import chord_pitch_classes


class CandidateScorer:
    def is_valid(self, segment: MusicSegment, melody_track_id: str, pitch_range: tuple[int, int]) -> bool:
        all_notes = sorted(
            [note for note in segment.notes if note.track_id == melody_track_id],
            key=lambda item: (item.beat, item.pitch),
        )
        tagged_theme = [note for note in all_notes if note.voice_role == "theme"]
        notes = sorted(
            tagged_theme or [note for note in all_notes if note.voice_role is None],
            key=lambda item: item.beat,
        )
        if len(notes) < 8:
            return False
        if any(note.pitch < pitch_range[0] or note.pitch > pitch_range[1] for note in all_notes):
            return False
        if any(note.beat + note.duration_beats > segment.total_beats + 0.001 for note in all_notes):
            return False
        if any(left.beat + left.duration_beats > right.beat + 0.001 for left, right in zip(notes, notes[1:])):
            return False
        if not self._valid_polyphony(all_notes, segment.actual_max_voices):
            return False
        if not self._valid_harmony(all_notes, segment):
            return False
        if any(
            note.voice_role == "ornament" and note.duration_beats > 0.5
            for note in all_notes
        ):
            return False
        in_scale = set(scale_notes(root_pc(segment.root_note), segment.scale, 0, 127))
        ratio = sum(note.pitch in in_scale for note in notes) / len(notes)
        if ratio < (0.8 if segment.emotion == "tense" else 0.9):
            return False
        leaps = [abs(right.pitch - left.pitch) for left, right in zip(notes, notes[1:])]
        if leaps and sum(leap > 7 for leap in leaps) / len(leaps) > 0.1:
            return False
        if max(note.pitch for note in notes) - min(note.pitch for note in notes) > 16:
            return False
        return True

    def score(self, segment: MusicSegment, melody_track_id: str) -> float:
        all_notes = [note for note in segment.notes if note.track_id == melody_track_id]
        tagged_theme = [note for note in all_notes if note.voice_role == "theme"]
        notes = sorted(
            tagged_theme or [note for note in all_notes if note.voice_role is None],
            key=lambda item: item.beat,
        )
        if not notes:
            return float("-inf")
        intervals = [abs(right.pitch - left.pitch) for left, right in zip(notes, notes[1:])]
        stepwise = sum(interval <= 4 for interval in intervals) / max(1, len(intervals))
        motif = [note.pitch for note in notes if note.beat < segment.beats_per_bar]
        second_bar = [note.pitch for note in notes if segment.beats_per_bar <= note.beat < segment.beats_per_bar * 2]
        repeated = self._similarity(motif, second_bar)
        cadence = 1.0 if notes[-1].duration_beats >= 0.75 else 0.0
        return stepwise * 0.5 + repeated * 0.3 + cadence * 0.2

    @staticmethod
    def _valid_polyphony(notes, maximum: int) -> bool:
        by_beat: dict[float, list] = {}
        for note in notes:
            by_beat.setdefault(round(note.beat, 3), []).append(note)
        for onset in by_beat.values():
            if len({note.pitch for note in onset}) != len(onset):
                return False
            if len(onset) > maximum:
                return False
            theme = next((note for note in onset if note.voice_role == "theme"), None)
            harmony = [note for note in onset if note.voice_role == "harmony"]
            if theme and any(note.pitch >= theme.pitch for note in harmony):
                return False
        return True

    @staticmethod
    def _valid_harmony(notes, segment: MusicSegment) -> bool:
        if not segment.harmony:
            return True
        for note in notes:
            if note.voice_role != "harmony":
                continue
            bar = min(
                int(note.beat // segment.beats_per_bar),
                len(segment.harmony) - 1,
            )
            if note.pitch % 12 not in chord_pitch_classes(
                segment.root_note, segment.harmony[bar]
            ):
                return False
        return True

    @staticmethod
    def _similarity(left: list[int], right: list[int]) -> float:
        count = min(len(left), len(right))
        if count == 0:
            return 0.0
        return sum(abs(left[index] - right[index]) <= 2 for index in range(count)) / count
