from pathlib import Path
import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.music.config_loader import MusicConfigStore
from app.music.generation.composer import RuleComposer
from app.music.generation.scoring import CandidateScorer


class SegmentComposerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        cls.config = MusicConfigStore(defaults).active_config
        cls.composer = RuleComposer()
        cls.scorer = CandidateScorer()

    def test_rule_segment_is_four_bars_and_valid(self) -> None:
        emotion = EmotionMapper().from_tuple(8, 7, 0.85, 0.15, source="simulator")
        segment = self.composer.compose(
            emotion,
            "neutral",
            92,
            self.config.tracks,
        )
        melody = next(track for track in self.config.tracks if track.role == "melody")
        self.assertEqual(segment.total_beats, 16)
        self.assertTrue(segment.notes)
        self.assertTrue(self.scorer.is_valid(segment, melody.id, melody.pitch_range))
        self.assertTrue(all(note.beat + note.duration_beats <= 16 for note in segment.notes))

    def test_previous_segment_keeps_first_note_within_a_fifth(self) -> None:
        mapper = EmotionMapper()
        first = self.composer.compose(
            mapper.from_tuple(8, 7, 0.9, 0.1, source="simulator"),
            "neutral",
            92,
            self.config.tracks,
        )
        second = self.composer.compose(
            mapper.from_tuple(7, 3, 0.8, 0.2, source="simulator"),
            first.emotion,
            84,
            self.config.tracks,
            previous=first,
        )
        melody_id = next(track.id for track in self.config.tracks if track.role == "melody")
        first_notes = [note for note in first.notes if note.track_id == melody_id]
        second_notes = [note for note in second.notes if note.track_id == melody_id]
        self.assertLessEqual(abs(second_notes[0].pitch - first_notes[-1].pitch), 7)


if __name__ == "__main__":
    unittest.main()
