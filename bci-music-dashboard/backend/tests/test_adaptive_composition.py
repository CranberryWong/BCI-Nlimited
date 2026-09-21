import unittest

from app.adaptive.composition import CounterpointStrategy, FormEngine, HarmonyEngine, MelodyGuard, MotifEngine, TonalPlanner, motif_to_pianoroll
from app.adaptive.config import AdaptiveConfigStore
from app.adaptive.schemas import CanonicalMusicEvent, FormState, MotifNote, MotifPlan, MusicIntent, TonalPlan
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

    def propose(self, tonal, motif, form, rule, roles):
        result = {}
        if "bass" in roles:
            result["bass"] = [pitch + 12 for pitch in rule.bass_pitches]
        if "harmony" in roles:
            result["harmony"] = [[pitch + 12 for pitch in voicing] for voicing in rule.pad_voicings]
        if "inner_voice" in roles:
            result["inner_voice"] = [voicing[1] for voicing in rule.pad_voicings]
        return result


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

    async def test_motif_contour_subdivision_and_anchor_mutability_are_config_driven(self):
        config = self.store.get("motif")
        config["contours"]["low_valence"] = "ascending"
        config["valence_thresholds"] = {"low_below": 0.3, "high_above": 0.7}
        config["density_thresholds"] = {"medium_above": 0.2, "fast_above": 0.9}
        config["anchors"]["immutable"] = False
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(valence=0.2), True)
        form = FormEngine(self.store.get("form")).state.model_copy(update={"role": "identity"})
        plan = MotifEngine(config).plan(intent(valence=0.2, density=0.5), tonal, form)
        self.assertEqual(plan.contour, "ascending")
        self.assertAlmostEqual(plan.notes[1].beat - plan.notes[0].beat, 0.5)
        self.assertTrue(plan.notes[0].anchor)
        self.assertTrue(plan.notes[0].mutable)

    async def test_every_configured_motif_transform_changes_the_plan_as_designed(self):
        config = self.store.get("motif")
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        state = FormEngine(self.store.get("form")).state
        engine = MotifEngine(config)
        identity = engine.plan(intent(density=0.6), tonal, state.model_copy(update={"role": "identity"}))

        simplified = engine.plan(intent(density=0.6), tonal, state.model_copy(update={"role": "intro"}))
        self.assertLess(len(simplified.notes), len(identity.notes))

        transposed = engine.plan(intent(density=0.6), tonal, state.model_copy(update={"role": "contrast"}))
        self.assertTrue(any(
            after.pitch != before.pitch
            for before, after in zip(identity.notes, transposed.notes)
            if before.mutable
        ))
        self.assertEqual(
            [note.pitch for note in transposed.notes if note.anchor],
            [note.pitch for note in identity.notes if note.anchor],
        )

        inverted = engine.plan(intent(density=0.6), tonal, state.model_copy(update={"role": "development"}))
        self.assertTrue(any(
            after.pitch != before.pitch
            for before, after in zip(identity.notes, inverted.notes)
            if before.mutable
        ))

        compressed = engine.plan(intent(density=0.6), tonal, state.model_copy(update={"role": "climax"}))
        self.assertGreater(len(compressed.notes), len(identity.notes))

        recalled = engine.plan(intent(density=0.9), tonal, state.model_copy(update={"role": "return"}))
        self.assertEqual(
            [(note.beat, note.pitch) for note in recalled.notes],
            [(note.beat, note.pitch) for note in identity.notes],
        )

        cadence_engine = MotifEngine(self.store.get("motif"))
        cadence = cadence_engine.plan(intent(density=0.6), tonal, state.model_copy(update={"role": "coda"}))
        self.assertEqual(cadence.notes[-1].pitch % 12, 0)
        self.assertEqual(cadence.notes[-1].duration_beats, 0.5)

    async def test_form_never_changes_before_two_phrases(self):
        engine = FormEngine(self.store.get("form"))
        initial = engine.state.section_id
        first, changed = engine.advance_phrase(intent(transition_urgency=1.0))
        self.assertFalse(changed)
        self.assertEqual(first.section_id, initial)
        second, changed = engine.advance_phrase(intent(transition_urgency=1.0))
        self.assertTrue(changed)
        self.assertNotEqual(second.section_id, initial)

    async def test_stable_emotion_traverses_every_section_at_the_maximum(self):
        config = self.store.get("form")
        engine = FormEngine(config)
        visited = [engine.state.section_id]
        stable = intent(transition_urgency=0.0, confidence=0.9)
        while not engine.state.completed:
            previous = engine.state.section_id
            state, changed = engine.advance_phrase(stable)
            if changed:
                self.assertEqual(state.phrase_in_section, 0)
                visited.append(state.section_id)
            elif not state.completed and state.section_id != config["sections"][-1]["id"]:
                self.assertLess(state.phrase_in_section, config["maximum_phrases_per_section"])
            self.assertGreaterEqual(state.phrase_index, 1)
        self.assertEqual(visited, [section["id"] for section in config["sections"]])
        self.assertEqual(engine.state.section_id, "coda")
        self.assertTrue(engine.state.is_final)
        self.assertTrue(engine.state.completed)

    async def test_low_confidence_cannot_trigger_early_transition(self):
        engine = FormEngine(self.store.get("form"))
        uncertain = intent(transition_urgency=1.0, confidence=0.59)
        for _ in range(3):
            state, changed = engine.advance_phrase(uncertain)
            self.assertFalse(changed)
            self.assertEqual(state.section_id, "intro")
        state, changed = engine.advance_phrase(uncertain)
        self.assertTrue(changed)
        self.assertEqual(state.section_id, "A1")

    async def test_emotion_budget_limits_early_not_structural_transitions(self):
        config = self.store.get("form")
        config["emotion_change_budget"] = 0
        engine = FormEngine(config)
        urgent = intent(transition_urgency=1.0, confidence=1.0)
        while engine.state.section_id != "B":
            state, _ = engine.advance_phrase(urgent)
        self.assertEqual(state.emotion_changes_used, 0)
        self.assertEqual(state.phrase_index, 6)

    async def test_completed_coda_is_terminal(self):
        engine = FormEngine(self.store.get("form"))
        urgent = intent(transition_urgency=1.0, confidence=1.0)
        while not engine.state.completed:
            engine.advance_phrase(urgent)
        terminal = engine.state.model_dump()
        state, changed = engine.advance_phrase(urgent)
        self.assertFalse(changed)
        self.assertEqual(state.model_dump(), terminal)

    async def test_notochord_is_optional_harmony_candidate_only(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        form = FormEngine(self.store.get("form")).state
        motif = MotifEngine(self.store.get("motif")).plan(intent(), tonal, form)
        config = self.store.get("harmony")
        config["notochord"]["enabled"] = True
        config["notochord"]["roles"] = ["bass"]
        plan = await HarmonyEngine(config, FakeNotoProvider()).plan(tonal, motif, form)
        self.assertEqual(plan.provider, "notochord")
        self.assertEqual(plan.chords, ["I", "IV", "V", "I"])
        self.assertTrue(all(note.anchor for note in motif.notes if note.anchor))

    async def test_chord_quality_controls_pad_voicing(self):
        tonal = TonalPlan(root_note="C", scale="major", pitch_classes=[0, 2, 4, 5, 7, 9, 11])
        form = FormState(section_id="A1", role="identity")
        motif = MotifPlan(id="quality")
        config = self.store.get("harmony")
        config["progressions"]["identity"] = ["I", "ii", "vii°"]
        plan = await HarmonyEngine(config).plan(tonal, motif, form)
        self.assertEqual([[pitch % 12 for pitch in chord] for chord in plan.pad_voicings], [
            [0, 4, 7], [2, 5, 9], [11, 2, 5],
        ])

    async def test_notochord_only_changes_selected_roles(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        form = FormEngine(self.store.get("form")).state
        motif = MotifEngine(self.store.get("motif")).plan(intent(), tonal, form)
        config = self.store.get("harmony")
        config["notochord"]["enabled"] = True
        config["notochord"]["roles"] = ["harmony", "inner_voice"]
        plan = await HarmonyEngine(config, FakeNotoProvider()).plan(tonal, motif, form)
        rule = await HarmonyEngine({**config, "notochord": {"enabled": False}}).plan(tonal, motif, form)
        self.assertEqual(plan.bass_pitches, rule.bass_pitches)
        self.assertNotEqual(plan.pad_voicings, rule.pad_voicings)
        self.assertEqual(len(plan.inner_pitches), len(plan.chords))
        self.assertEqual(plan.notochord_roles, ["harmony", "inner_voice"])

    async def test_counterpoint_interval_direction_and_parallel_switches(self):
        motif = MotifPlan(
            id="parallel",
            bars=1,
            beats_per_bar=4,
            notes=[
                MotifNote(beat=0, duration_beats=1, pitch=60, velocity=80),
                MotifNote(beat=1, duration_beats=1, pitch=62, velocity=80),
                MotifNote(beat=2, duration_beats=1, pitch=64, velocity=80),
            ],
        )
        tonal = TonalPlan(root_note="C", scale="major", pitch_classes=[0, 2, 4, 5, 7, 9, 11])
        form = FormState(section_id="B", role="contrast")
        base = {
            "enabled": True, "maximum_voices": 2, "forms": ["contrast"],
            "entry_delay_beats": 0, "interval_semitones": 7, "allow_inversion": False,
            "reject_parallel_fifths": False, "reject_parallel_octaves": False,
        }
        allowed = CounterpointStrategy(base).generate(motif, tonal, form)
        self.assertEqual([note.pitch for note in allowed], [67, 69, 71])
        rejected = CounterpointStrategy({**base, "reject_parallel_fifths": True}).generate(motif, tonal, form)
        self.assertEqual(rejected[0].pitch, 67)
        self.assertNotEqual(rejected[1].pitch, 69)
        disabled = CounterpointStrategy({**base, "maximum_voices": 1}).generate(motif, tonal, form)
        self.assertEqual(disabled, [])

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

    async def test_guard_uses_selected_soft_grid(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        event = CanonicalMusicEvent(
            role="marimba", track_id="marimba", type="note_on",
            beat=0.49, pitch=60, velocity=80, duration_ms=90,
        )
        quarter_config = self.store.get("melody")
        quarter_config["guardrails"]["soft_grid"] = "1/4"
        eighth_config = self.store.get("melody")
        eighth_config["guardrails"]["soft_grid"] = "1/8"
        self.assertEqual(MelodyGuard(quarter_config).apply(event, tonal, None, 1.0).beat, 0.49)
        self.assertEqual(MelodyGuard(eighth_config).apply(event, tonal, None, 1.0).beat, 0.5)

    async def test_guard_respects_minor_and_diminished_chord_quality(self):
        tonal = TonalPlanner(self.store.get("tonal")).plan(intent(), True)
        config = self.store.get("melody")
        config["guardrails"]["scale_snap"] = False
        minor_event = CanonicalMusicEvent(
            role="marimba", track_id="marimba", type="note_on",
            beat=1.0, pitch=66, velocity=80, duration_ms=90,
        )
        minor = MelodyGuard(config).apply(minor_event, tonal, 2, 0.7, "ii")
        self.assertIn(minor.pitch % 12, {2, 5, 9})
        self.assertNotEqual(minor.pitch % 12, 6)

        diminished_event = minor_event.model_copy(update={"pitch": 63})
        diminished = MelodyGuard(config).apply(diminished_event, tonal, 11, 0.7, "vii°")
        self.assertIn(diminished.pitch % 12, {11, 2, 5})


if __name__ == "__main__":
    unittest.main()
