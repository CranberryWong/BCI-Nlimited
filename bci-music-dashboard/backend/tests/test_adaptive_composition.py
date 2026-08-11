import unittest

from app.adaptive.composition import FormEngine, HarmonyEngine, MelodyGuard, MotifEngine, TonalPlanner, motif_to_pianoroll
from app.adaptive.config import AdaptiveConfigStore
from app.adaptive.schemas import CanonicalMusicEvent, MusicIntent
from app.core.config import get_settings


def intent(**updates):
    values = {
        "valence": 0.7, "energy": 0.6, "tension": 0.2, "density": 0.6,
        "brightness": 0.7, "pulse": 0.6, "complexity": 0.5,
        "register_band": "mid_high", "articulation": "balanced",
        "spatial_width": 0.5, "transition_urgency": 0.7, "confidence": 0.9,
    }
    values.update(updates)
    return MusicIntent(**values)


class FakeNotoProvider:
    available = True

    def propose(self, tonal, motif, form, rule):
        return [pitch + 12 for pitch in rule.bass_pitches]


class AdaptiveCompositionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.store = AdaptiveConfigStore(get_settings().adaptive_config_dir)

    async def test_seeded_motif_and_midi_steering_are_reproducible(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        form = FormEngine(self.store.get("form")).state
        left = MotifEngine(self.store.get("motif"), seed=42).plan(intent(), tonal, form)
        right = MotifEngine(self.store.get("motif"), seed=42).plan(intent(), tonal, form)
        self.assertEqual(left.model_dump(), right.model_dump())
        roll = motif_to_pianoroll(left, 0.0)
        self.assertEqual(len(roll), 128)
        self.assertEqual(roll[left.notes[0].pitch], 2)

    async def test_form_never_changes_before_two_phrases(self):
        engine = FormEngine(self.store.get("form"))
        initial = engine.state.section_id
        first, changed = engine.advance_phrase(intent(transition_urgency=1.0))
        self.assertFalse(changed)
        self.assertEqual(first.section_id, initial)
        second, changed = engine.advance_phrase(intent(transition_urgency=1.0))
        self.assertTrue(changed)
        self.assertNotEqual(second.section_id, initial)

    async def test_notochord_is_optional_harmony_candidate_only(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        form = FormEngine(self.store.get("form")).state
        motif = MotifEngine(self.store.get("motif")).plan(intent(), tonal, form)
        config = self.store.get("harmony")
        config["notochord"]["enabled"] = True
        plan = await HarmonyEngine(config, FakeNotoProvider()).plan(tonal, motif, form)
        self.assertEqual(plan.provider, "notochord")
        self.assertEqual(plan.chords, ["I", "IV", "V", "I"])
        self.assertTrue(all(note.anchor for note in motif.notes if note.anchor))

    async def test_guard_limits_range_and_snaps_to_scale(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        event = CanonicalMusicEvent(role="marimba", track_id="marimba", type="note_on", pitch=121, velocity=80, duration_ms=10)
        guarded = MelodyGuard(self.store.get("melody")).apply(event, tonal, tonal.pitch_classes[0], 0.7)
        self.assertGreaterEqual(guarded.pitch, 48)
        self.assertLessEqual(guarded.pitch, 96)
        self.assertGreaterEqual(guarded.duration_ms, 80)
        second = CanonicalMusicEvent(role="marimba", track_id="marimba", type="note_on", beat=1.0, pitch=50, velocity=80, duration_ms=90)
        guard = MelodyGuard(self.store.get("melody"))
        corrected = guard.apply(second, tonal, 0, 0.7)
        self.assertIn(corrected.pitch % 12, {0, 4, 7})
        self.assertTrue(corrected.metadata["strong_beat_corrected"])
        note_off = second.model_copy(update={"type": "note_off", "velocity": 0, "duration_ms": 0})
        released = guard.apply(note_off, tonal, 0, 0.7)
        self.assertEqual(released.pitch, corrected.pitch)


if __name__ == "__main__":
    unittest.main()
