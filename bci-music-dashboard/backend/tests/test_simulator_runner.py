import random
import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.bci.simulator_runner import SimulatorRunner


async def ignore_payload(*_payload: float) -> None:
    pass


class SimulatorRunnerTest(unittest.TestCase):
    def test_continuous_signal_stays_bounded_and_limits_each_step(self) -> None:
        runner = SimulatorRunner(ignore_payload, rng=random.Random(7))
        runner._reset_session(0.0)
        previous_valence, previous_arousal = runner.valence, runner.arousal

        for second in range(1, 91):
            valence, arousal, confidence, inverse_confidence = runner._next_payload(float(second))
            self.assertGreaterEqual(valence, 1.0)
            self.assertLessEqual(valence, 9.0)
            self.assertGreaterEqual(arousal, 1.0)
            self.assertLessEqual(arousal, 9.0)
            self.assertLessEqual(abs(valence - previous_valence), runner.MAX_STEP_PER_SECOND + 1e-9)
            self.assertLessEqual(abs(arousal - previous_arousal), runner.MAX_STEP_PER_SECOND + 1e-9)
            self.assertGreaterEqual(confidence, 0.55)
            self.assertLessEqual(confidence, 0.96)
            self.assertAlmostEqual(confidence + inverse_confidence, 1.0)
            previous_valence, previous_arousal = valence, arousal

    def test_target_changes_follow_the_adjacent_emotion_graph(self) -> None:
        runner = SimulatorRunner(ignore_payload, rng=random.Random(3))
        runner.target_label = "calm"

        for second in range(1, 30):
            previous = runner.target_label
            runner._choose_next_target(float(second))
            self.assertIn(runner.target_label, runner.ADJACENT_TARGETS[previous])

    def test_mapper_preserves_continuous_axes_while_exposing_integer_classes(self) -> None:
        emotion = EmotionMapper().from_tuple(6.4, 3.2, 0.8, 0.2, source="simulator")

        self.assertEqual(emotion.valence_class, 6)
        self.assertEqual(emotion.arousal_class, 3)
        self.assertAlmostEqual(emotion.valence_norm, (6.4 - 1) / 8)
        self.assertAlmostEqual(emotion.arousal_norm, (3.2 - 1) / 8)
