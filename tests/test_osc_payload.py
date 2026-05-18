import unittest

from server.outputs.osc import OscPayload


class OscPayloadTest(unittest.TestCase):
    def test_osc_payload_shape(self):
        self.assertEqual(OscPayload(1, 7, 0.5, 0.7).to_list(), [1, 7, 0.5, 0.7])

    def test_osc_payload_defaults_missing_probabilities(self):
        self.assertEqual(OscPayload(5, 5).to_list(), [5, 5, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()

