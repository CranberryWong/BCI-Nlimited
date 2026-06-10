from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.storage.presets import PresetStore


class PresetStoreTest(unittest.TestCase):
    def test_saved_preset_is_active_and_listed(self) -> None:
        with TemporaryDirectory() as directory:
            store = PresetStore(Path(directory))
            saved = store.save("Dense Piano", {"global": {}, "default_tracks": []})
            presets = store.list()

            self.assertEqual(saved["id"], "dense-piano")
            self.assertTrue(saved["active"])
            self.assertTrue(any(item["id"] == "dense-piano" and item["active"] for item in presets))
            reloaded = PresetStore(Path(directory))
            self.assertEqual(reloaded.active_id, "dense-piano")

    def test_loaded_builtin_becomes_active(self) -> None:
        with TemporaryDirectory() as directory:
            store = PresetStore(Path(directory))
            defaults = {
                "global": {"output_mode": "mock"},
                "default_tracks": [],
            }
            store.load("ambient-neurofeedback", defaults)

            active = [item for item in store.list() if item["active"]]
            self.assertEqual([item["id"] for item in active], ["ambient-neurofeedback"])


if __name__ == "__main__":
    unittest.main()
