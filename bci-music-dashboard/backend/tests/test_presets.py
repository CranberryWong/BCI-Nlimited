from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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

    def test_saving_the_same_name_replaces_the_existing_custom_preset(self) -> None:
        with TemporaryDirectory() as directory:
            store = PresetStore(Path(directory))
            store.save("My Preset", {"global": {"bpm": 96}, "default_tracks": []})
            store.save("My Preset", {"global": {"bpm": 120}, "default_tracks": []})

            self.assertEqual(len([item for item in store.list() if item["id"] == "my-preset"]), 1)
            loaded = store.load("my-preset", {"global": {}, "default_tracks": []})
            self.assertEqual(loaded["global"]["bpm"], 120)

    def test_open_folder_reveals_the_preset_directory(self) -> None:
        with TemporaryDirectory() as directory:
            store = PresetStore(Path(directory))
            with patch("app.storage.presets.subprocess.Popen") as open_folder:
                store.open_folder()

            open_folder.assert_called_once()
            self.assertEqual(open_folder.call_args.args[0], ["open", str(Path(directory))])


if __name__ == "__main__":
    unittest.main()
