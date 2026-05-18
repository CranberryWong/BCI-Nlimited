import unittest

from server.config import AppConfig


class ConfigTest(unittest.TestCase):
    def test_config_update_casts_numbers(self):
        config = AppConfig()
        config.update({"osc_target_port": "8001", "midi_channel": "2"})
        self.assertEqual(config.osc_target_port, 8001)
        self.assertEqual(config.midi_channel, 2)


if __name__ == "__main__":
    unittest.main()

