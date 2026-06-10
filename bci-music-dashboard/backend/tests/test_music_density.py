from pathlib import Path
import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.music.config_loader import MusicConfigStore
from app.music.engine import MusicEngine
from app.music.schemas import TrackConfig


class StubOutput:
    def send_event(self, *_args) -> None:
        pass

    def send_emotion(self, *_args) -> None:
        pass


class MusicDensityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        cls.config = MusicConfigStore(defaults).active_config
        cls.engine = MusicEngine(cls.config, StubOutput(), StubOutput())
        cls.emotion = EmotionMapper().from_tuple(8, 7, 0.8, 0.2, source="simulator")

    def test_legacy_track_defaults_to_single_voice(self) -> None:
        track = TrackConfig.model_validate(
            {
                "id": "legacy",
                "name": "Legacy",
                "role": "melody",
                "instrument": "piano",
            }
        )
        self.assertEqual(track.polyphony, 1)

    def test_melody_polyphony_controls_simultaneous_note_count(self) -> None:
        track = next(track for track in self.config.tracks if track.role == "melody").model_copy(deep=True)
        track.polyphony = 3
        events = self.engine._melody(track, self.emotion)
        note_ons = [event for event in events if event.type == "note_on"]
        self.assertEqual(len(note_ons), 3)
        self.assertEqual(len({event.pitch for event in note_ons}), 3)

    def test_pad_polyphony_controls_chord_size(self) -> None:
        track = next(track for track in self.config.tracks if track.role == "pad").model_copy(deep=True)
        track.polyphony = 5
        events = self.engine._pad(track, self.emotion)
        note_ons = [event for event in events if event.type == "note_on"]
        self.assertEqual(len(note_ons), 5)
        self.assertEqual(len({event.pitch for event in note_ons}), 5)

    def test_bass_polyphony_adds_harmonic_support(self) -> None:
        track = next(track for track in self.config.tracks if track.role == "bass").model_copy(deep=True)
        track.polyphony = 2
        events = self.engine._bass(track, self.emotion)
        note_ons = [event for event in events if event.type == "note_on"]
        self.assertEqual(len(note_ons), 2)
        self.assertEqual(len({event.pitch for event in note_ons}), 2)


if __name__ == "__main__":
    unittest.main()
