import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.music.generation.emotion_window import EmotionWindowAggregator


class EmotionWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = 100.0
        self.aggregator = EmotionWindowAggregator(
            window_seconds=16,
            minimum_samples=4,
            clock=lambda: self.now,
        )
        self.mapper = EmotionMapper()

    def add(self, valence: int, arousal: int, confidence: float, timestamp: float) -> None:
        emotion = self.mapper.from_tuple(valence, arousal, confidence, 1 - confidence, source="simulator")
        emotion.timestamp = timestamp
        self.aggregator.add(emotion)

    def test_fewer_than_four_samples_returns_neutral(self) -> None:
        for offset in range(3):
            self.add(9, 9, 0.9, self.now - offset)
        self.assertEqual(self.aggregator.aggregate().label, "neutral")

    def test_confidence_weighted_window_ignores_old_samples(self) -> None:
        self.add(1, 1, 0.9, self.now - 20)
        for offset in range(4):
            self.add(9, 9, 0.9, self.now - offset)
        result = self.aggregator.aggregate()
        self.assertEqual(result.label, "joy")
        self.assertGreater(result.valence_norm, 0.9)

    def test_hysteresis_requires_two_windows_for_small_change(self) -> None:
        for offset in range(4):
            self.add(7, 3, 0.7, self.now - offset)
        first = self.aggregator.aggregate()
        second = self.aggregator.aggregate()
        self.assertEqual(first.label, "neutral")
        self.assertEqual(second.label, "calm")


if __name__ == "__main__":
    unittest.main()
