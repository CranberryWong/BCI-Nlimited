import copy
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from app.adaptive.config import AdaptiveConfigStore, MODULES
from app.adaptive.legacy import merge_legacy_music_config
from app.music.recorder import SessionRecorder


CONFIG_DIR = Path(__file__).resolve().parents[1] / "app" / "config"


class AdaptiveConfigLegacyTest(unittest.TestCase):
    def test_configuration_locks_and_validates_as_one_snapshot(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for module in MODULES:
                shutil.copy(CONFIG_DIR / f"{module}.yaml", root / f"{module}.yaml")
            store = AdaptiveConfigStore(root)
            store.lock()
            with self.assertRaises(RuntimeError):
                store.replace("form", store.get("form"))
            store.unlock()
            invalid = store.get("melody")
            invalid["worker_url"] = "ws://example.com:8766/v1/stream"
            with self.assertRaisesRegex(ValueError, "localhost"):
                store.replace("melody", invalid)
            valid = store.get("melody")
            valid["audio"]["gain"] = 0.1
            store.replace("melody", valid)
            persisted = yaml.safe_load((root / "melody.yaml").read_text())
            self.assertEqual(persisted["audio"]["gain"], 0.1)

    def test_legacy_track_endpoints_become_disabled_central_targets(self):
        store = AdaptiveConfigStore(CONFIG_DIR)
        adaptive = store.all()
        legacy = {
            "default_tracks": [{
                "role": "melody", "enabled": True, "density": 0.5,
                "velocity_range": [40, 80], "midi_channel": 4,
                "target_ip": "10.0.0.4", "target_port": 57120,
            }]
        }
        migrated, changes = merge_legacy_music_config(adaptive, legacy)
        target = next(item for item in migrated["outputs"]["osc"]["targets"] if item["host"] == "10.0.0.4")
        self.assertFalse(target["enabled"])
        self.assertTrue(target["migrated_from_track_routing"])
        self.assertTrue(changes)

    def test_session_recorder_resolves_adaptive_artifacts_safely(self):
        with tempfile.TemporaryDirectory() as raw:
            recorder = SessionRecorder(Path(raw))
            session = Path(raw) / "session-1"
            magenta = session / "magenta"
            magenta.mkdir(parents=True)
            (session / "adaptive_summary.json").write_text("{}")
            (magenta / "take.wav").write_bytes(b"RIFF")
            self.assertEqual(recorder.artifact("session-1", "summary").name, "adaptive_summary.json")
            self.assertEqual(recorder.artifact("session-1", "wav").name, "take.wav")
            with self.assertRaises(FileNotFoundError):
                recorder.artifact("../outside", "summary")


if __name__ == "__main__":
    unittest.main()
