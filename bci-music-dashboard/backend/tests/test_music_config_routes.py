from pathlib import Path
from types import SimpleNamespace
import unittest

from app.api.routes_music import put_music_config
from app.music.config_loader import MusicConfigStore


BACKEND = Path(__file__).resolve().parents[1]


class StubRuntime:
    def __init__(self) -> None:
        self.apply_count = 0

    def apply_config(self) -> None:
        self.apply_count += 1


class MusicConfigRouteTest(unittest.TestCase):
    def test_apply_keeps_editor_field_metadata(self):
        store = MusicConfigStore(BACKEND / "app/config/music_defaults.yaml")
        runtime = StubRuntime()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config_store=store, runtime=runtime)))

        response = put_music_config(store.active_config.as_api(), request)

        self.assertEqual(runtime.apply_count, 1)
        self.assertEqual(response["global"]["root_note"], "C")
        self.assertEqual(response["default_schema"]["global"]["root_note"]["options"][0], "C")
        self.assertEqual(response["default_schema"]["global"]["quantization"]["options"][3], "1/8")
        self.assertIn("midi", response["default_schema"]["global"]["output_mode"]["options"])
