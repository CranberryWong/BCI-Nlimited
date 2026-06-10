import unittest

from app.music.osc_output import OscOutput
from app.music.schemas import TrackConfig


class OscOutputTargetTest(unittest.TestCase):
    def test_docker_default_redirects_localhost_to_host(self) -> None:
        output = OscOutput("host.docker.internal", 57120)
        track = TrackConfig.model_validate(
            {
                "id": "track",
                "name": "Track",
                "role": "melody",
                "instrument": "piano",
                "target_ip": "127.0.0.1",
                "target_port": 57120,
            }
        )
        self.assertEqual(output._target(track), ("host.docker.internal", 57120))

    def test_explicit_remote_target_is_preserved(self) -> None:
        output = OscOutput("host.docker.internal", 6000)
        track = TrackConfig.model_validate(
            {
                "id": "track",
                "name": "Track",
                "role": "melody",
                "instrument": "piano",
                "target_ip": "192.168.1.20",
                "target_port": 7000,
            }
        )
        self.assertEqual(output._target(track), ("192.168.1.20", 7000))


if __name__ == "__main__":
    unittest.main()
