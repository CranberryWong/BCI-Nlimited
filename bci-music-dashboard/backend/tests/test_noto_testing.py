import unittest
from pathlib import Path

from app.bci.emotion_mapper import EmotionMapper
from app.music.config_loader import MusicConfigStore
from app.music.generation.noto_testing import NotoTestingRuntime
from app.music.generation.portrait_library import PortraitLibrary


class FakeNotochord:
    def __init__(self):
        self.reset_count = 0
        self.feed_events = []

    def reset(self):
        self.reset_count += 1

    def query(self, **kwargs):
        return {
            "inst": kwargs["next_inst"],
            "pitch": min(kwargs["include_pitch"]),
            "time": kwargs["min_time"],
            "vel": kwargs["min_vel"],
        }

    def feed(self, *event):
        self.feed_events.append(event)


class FakeModel:
    active_provider = "notochord"
    loaded = True
    detail = "ready:notochord:cpu"

    def __init__(self):
        self.model = FakeNotochord()


class MissingModel:
    active_provider = "rule"
    loaded = False
    model = None
    detail = "model_missing"


class NotoTestingRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.config = MusicConfigStore(root / "backend/app/config/music_defaults.yaml").active_config
        cls.library = PortraitLibrary(root / "music_library")

    def _runtime(self):
        self.events = []

        async def broadcast(_message):
            pass

        return NotoTestingRuntime(self.library, self.config, FakeModel(), self.events.append, lambda: None, broadcast)

    @staticmethod
    def _emotion(label):
        values = {"calm": (8, 3), "joy": (8, 8), "tense": (2, 8), "sad": (2, 2), "neutral": (5, 5)}
        return EmotionMapper().from_tuple(*values[label], .9, .1, source="simulator")

    def test_each_emotion_uses_its_machine_loop_only_as_a_meter_reference(self):
        runtime = self._runtime()
        for label in self.config.emotion_profiles:
            asset = self.library.select(label, "loop")
            self.assertIsNotNone(asset)
            self.assertTrue(asset.id.endswith("_loop_machine"))
            runtime.asset = asset
            segment = runtime._compose_noto_segment(self._emotion(label))
            self.assertEqual(segment.portrait_asset_id, asset.id)
            self.assertTrue(segment.notes)
            self.assertTrue(all(note.generated_by == "notochord" for note in segment.notes))

    def test_ensemble_is_all_notochord_and_keeps_every_enabled_track_audible(self):
        runtime = self._runtime()
        runtime.asset = self.library.select("tense", "loop")
        segment = runtime._compose_noto_segment(self._emotion("tense"))
        enabled = {track.id: track for track in self.config.tracks if track.enabled and track.compute_enabled}
        self.assertEqual({note.track_id for note in segment.notes}, set(enabled))
        self.assertTrue(all(note.generated_by == "notochord" for note in segment.notes))
        self.assertGreaterEqual(len(segment.notes), 16)
        for note in segment.notes:
            track = enabled[note.track_id]
            legal = runtime._sound_first_pitches(track)
            self.assertIn(note.pitch, legal)

    def test_profile_change_is_applied_when_a_new_segment_is_composed_without_resetting_model(self):
        runtime = self._runtime()
        runtime.asset = self.library.select("calm", "loop")
        runtime._compose_noto_segment(self._emotion("calm"))
        runtime._compose_noto_segment(self._emotion("joy"))
        self.assertEqual(runtime.current_emotion, "joy")
        self.assertEqual(runtime.model.model.reset_count, 0)
        self.assertGreater(runtime.current_bpm, self.config.emotion_profiles["calm"].bpm_range[0])

    def test_start_requires_notochord_and_never_uses_a_rule_fallback(self):
        async def broadcast(_message):
            pass

        runtime = NotoTestingRuntime(self.library, self.config, MissingModel(), lambda _event: None, lambda: None, broadcast)
        with self.assertRaisesRegex(ValueError, "loaded Notochord"):
            runtime.start()
