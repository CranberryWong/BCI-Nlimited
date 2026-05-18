import unittest

from server.outputs.midi import scale_1_9_to_0_127, scale_probability_to_0_127


class MidiMappingTest(unittest.TestCase):
    def test_scale_1_9_to_0_127_boundaries(self):
        self.assertEqual(scale_1_9_to_0_127(1), 0)
        self.assertEqual(scale_1_9_to_0_127(5), 64)
        self.assertEqual(scale_1_9_to_0_127(9), 127)

    def test_scale_probability_to_0_127_boundaries(self):
        self.assertEqual(scale_probability_to_0_127(0), 0)
        self.assertEqual(scale_probability_to_0_127(0.5), 64)
        self.assertEqual(scale_probability_to_0_127(1), 127)
        self.assertEqual(scale_probability_to_0_127(None), 0)


if __name__ == "__main__":
    unittest.main()

