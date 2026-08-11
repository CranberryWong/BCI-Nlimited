import asyncio
from pathlib import Path
import time
import tempfile
import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.music.config_loader import MusicConfigStore
from app.music.generation.model import MelodyModel
from app.music.generation.motif_library import MotifLibrary
from app.music.generation.portrait_library import PortraitAsset, PortraitLibrary, PortraitNote
from app.music.generation.scoring import CandidateScorer
from app.music.generation.runtime import MusicGenerationRuntime
from app.music.generation.form import CompositionStateMachine
from app.music.generation.theme_composer import ThemeComposer
from app.music.generation.theme_library import ThemeLibrary
from app.music.schemas import MusicGeneratorConfig, MusicSegment, SegmentNote
from test_motif_library import write_midi, write_yaml


class MusicGeneratorRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        project_root = Path(__file__).resolve().parents[2]
        self.music_config = MusicConfigStore(defaults).active_config
        self.theme_library = ThemeLibrary(project_root / "music_library")
        self.motif_library = MotifLibrary(project_root / "music_library")
        self.portrait_library = PortraitLibrary(project_root / "music_library")
        self.messages = []
        self.events = []

        async def broadcast(message):
            self.messages.append(message)

        self.runtime = MusicGenerationRuntime(
            MusicGeneratorConfig(inference_timeout_seconds=0.1),
            self.music_config,
            MelodyModel(Path("/missing/latest.pt"), Path("/missing/model_config.json")),
            self.theme_library,
            self.motif_library,
            self.portrait_library,
            self.events.append,
            lambda: None,
            broadcast,
            lambda _segment: None,
            lambda _status: None,
        )

    async def test_missing_model_keeps_theme_and_limits_bpm_step(self) -> None:
        self.runtime.config = self.runtime.config.model_copy(update={"composition_mode": "theme"})
        mapper = EmotionMapper()
        for _ in range(4):
            self.runtime.add_emotion(mapper.from_tuple(9, 9, 0.9, 0.1, source="simulator"))
        self.runtime.current_theme = self.theme_library.select("ode_to_joy")
        segment = await self.runtime._generate(self.runtime.form.current())
        self.assertEqual(segment.source, "theme")
        self.assertEqual(segment.theme_id, "ode_to_joy")
        self.assertEqual(segment.bars, 8)
        self.assertLessEqual(abs(segment.bpm - 84), 6)
        self.assertEqual(self.runtime.fallback_count, 0)

    async def test_system_mode_status_and_mode_switch(self) -> None:
        self.assertEqual(self.runtime.status()["system_mode"], "ENGAGING")
        status = await self.runtime.set_system_mode("MIRROR")

        self.assertEqual(status["system_mode"], "MIRROR")
        self.assertIsNone(status["engaging_stage"])
        self.assertEqual(self.messages[-2]["kind"], "mode_changed")
        self.assertEqual(self.messages[-1]["kind"], "generator_status")

    async def test_mirror_mode_uses_parameter_bpm_without_remapping_channels(self) -> None:
        mapper = EmotionMapper()
        await self.runtime.set_system_mode("MIRROR")
        for _ in range(4):
            self.runtime.add_emotion(mapper.from_tuple(9, 9, 0.9, 0.1, source="simulator"))
        self.runtime.current_theme = self.theme_library.select("ode_to_joy")

        segment = await self.runtime._generate(self.runtime.form.current())

        self.assertEqual(segment.emotion, "joy")
        self.assertLessEqual(abs(segment.bpm - 90), 6)
        melody_notes = [note for note in segment.notes if note.track_id == "piano_melody_01"]
        self.assertTrue(melody_notes)
        self.assertTrue(all(note.channel == 1 for note in melody_notes))

    async def test_engaging_regulation_redirects_tense_to_calmish_composition(self) -> None:
        mapper = EmotionMapper()
        for _ in range(4):
            self.runtime.add_emotion(mapper.from_tuple(9, 9, 0.9, 0.1, source="simulator"))
        self.runtime.current_theme = self.theme_library.select("ode_to_joy")
        self.runtime.mode_controller.started_at = time.monotonic() - 45

        segment = await self.runtime._generate(self.runtime.form.current())

        self.assertIn(segment.emotion, {"calm", "neutral"})
        status = self.runtime.status()
        self.assertEqual(status["system_mode"], "ENGAGING")
        self.assertEqual(status["engaging_stage"], "Regulation")
        self.assertIn("music_params", status)

    async def test_motif_mode_uses_approved_motif_and_keeps_melody_channel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            joy = root / "motifs" / "joy"
            joy.mkdir(parents=True)
            write_midi(joy / "approved.mid")
            write_yaml(joy / "approved.yaml", approved=True)
            self.runtime.motif_library = MotifLibrary(root)
            self.runtime.config = self.runtime.config.model_copy(update={"composition_mode": "motif"})
            mapper = EmotionMapper()
            for _ in range(4):
                self.runtime.add_emotion(mapper.from_tuple(9, 9, 0.9, 0.1, source="simulator"))
            self.runtime.current_theme = self.theme_library.select("ode_to_joy")

            segment = await self.runtime._generate(self.runtime.form.current())

            self.assertEqual(segment.source, "motif")
            self.assertEqual(segment.motif_id, "approved")
            melody_notes = [note for note in segment.notes if note.track_id == "piano_melody_01"]
            self.assertTrue(melody_notes)
            self.assertTrue(all(note.channel == 1 for note in melody_notes))
            self.assertTrue(any(note.track_id == "bass_01" for note in segment.notes))
            self.assertTrue(any(note.track_id == "drum_01" for note in segment.notes))

    async def test_stop_cancels_scheduled_note_tasks(self) -> None:
        emotion = EmotionMapper().from_tuple(5, 5, 0.8, 0.2, source="simulator")
        theme = self.theme_library.select("ode_to_joy")
        segment = self.runtime.composer.compose(
            theme,
            self.runtime.form.current(),
            emotion,
            "neutral",
            84,
            self.music_config.tracks,
            0.65,
            0.35,
        )
        self.runtime._schedule(segment)
        self.assertTrue(self.runtime.dispatch_tasks)
        await self.runtime.stop()
        self.assertFalse(self.runtime.dispatch_tasks)

    async def test_portrait_waits_for_initial_samples(self) -> None:
        self.runtime.config = self.runtime.config.model_copy(update={"composition_mode": "portrait"})
        self.runtime.start()
        await asyncio.sleep(0.05)

        self.assertFalse(self.runtime.initial_emotion_ready)
        self.assertIsNone(self.runtime.playing_segment)
        self.assertFalse(self.events)
        await self.runtime.stop()

    async def test_portrait_starts_with_stable_emotion_loop(self) -> None:
        self.runtime.config = self.runtime.config.model_copy(update={"composition_mode": "portrait"})
        mapper = EmotionMapper()
        for _ in range(4):
            self.runtime.add_emotion(mapper.from_tuple(8, 3, 0.9, 0.1, source="simulator"))

        self.runtime.start()
        await asyncio.sleep(0.05)

        self.assertTrue(self.runtime.initial_emotion_ready)
        self.assertEqual(self.runtime.active_portrait_emotion, "calm")
        self.assertIsNotNone(self.runtime.playing_segment)
        self.assertEqual(self.runtime.playing_segment.portrait_role, "loop")
        self.assertEqual(self.runtime.playing_segment.emotion, "calm")
        self.assertEqual(self.runtime.playing_segment.portrait_asset_id, "calm_001_loop_machine")
        await self.runtime.stop()

    async def test_portrait_label_change_releases_before_new_loop(self) -> None:
        self.runtime.active_portrait_emotion = "calm"
        self.runtime.last_portrait_role = "loop"
        mapper = EmotionMapper()
        tense = mapper.from_tuple(2, 8, 0.9, 0.1, source="simulator")
        calm = mapper.from_tuple(8, 3, 0.9, 0.1, source="simulator")

        self.assertEqual(self.runtime._portrait_role_for(tense, calm), "release")
        self.assertEqual(self.runtime.pending_portrait_emotion, "tense")
        self.runtime.active_portrait_emotion = self.runtime.pending_portrait_emotion
        self.runtime.pending_portrait_emotion = None
        self.runtime.last_portrait_role = "release"
        self.assertEqual(self.runtime._portrait_role_for(tense, tense), "loop")

    async def test_portrait_arousal_hysteresis(self) -> None:
        self.runtime.active_portrait_emotion = "joy"
        mapper = EmotionMapper()
        high = mapper.from_tuple(8, 8, 0.9, 0.1, source="simulator")
        medium = mapper.from_tuple(8, 5, 0.9, 0.1, source="simulator")
        low = mapper.from_tuple(8, 2, 0.9, 0.1, source="simulator")

        self.assertEqual(self.runtime._portrait_role_for(high, high), "tension")
        self.runtime.last_portrait_role = "tension"
        self.assertEqual(self.runtime._portrait_role_for(high, medium), "tension")
        self.assertEqual(self.runtime._portrait_role_for(high, low), "release")

    async def test_portrait_preserves_machine_xylophone_pitches(self) -> None:
        asset = self.portrait_library.select("neutral", "loop")
        emotion = EmotionMapper().from_tuple(5, 5, 0.9, 0.1, source="simulator")
        segment = self.runtime.portrait_composer.compose(
            asset,
            self.runtime._portrait_position("loop"),
            emotion,
            "neutral",
            self.music_config.tracks,
        )
        melody = [note for note in segment.notes if note.track_id == "piano_melody_01"]
        self.assertIn(36, [note.pitch for note in melody])
        starts: dict[int, list[float]] = {}
        for note in melody:
            starts.setdefault(note.pitch, []).append(note.beat * 60 / segment.bpm)
        self.assertTrue(all(
            later - earlier >= .999
            for values in starts.values()
            for earlier, later in zip(values, values[1:])
        ))

    async def test_portrait_harmony_is_opt_in_and_uses_the_global_bpm(self) -> None:
        melody_track = next(track for track in self.music_config.tracks if track.role == "melody")
        asset = PortraitAsset(
            id="sad-test", title="Sad Test", emotion="sad", role="loop", meter="4/4",
            bars=4, beats_per_bar=4, bpm=66, home_key="A", mode="minor", cadence="open",
            loopable=True, same_key_minimum_interval_seconds=1.0,
            notes=tuple(
                PortraitNote(beat=beat, duration_beats=1.5, pitch=pitch, velocity=80, source_track="Xylophone")
                for beat, pitch in ((0, 69), (4, 71), (8, 72), (12, 69))
            ),
            path=Path("/portrait-test"),
        )
        emotion = EmotionMapper().from_tuple(2, 2, 0.9, 0.1, source="simulator")
        position = self.runtime._portrait_position("loop")

        disabled = self.runtime.portrait_composer.compose(
            asset, position, emotion, "sad", self.music_config.tracks, bpm=120,
        )
        enabled = self.runtime.portrait_composer.compose(
            asset, position, emotion, "sad", self.music_config.tracks, bpm=120,
            harmony_enabled=True,
        )
        arpeggiated = self.runtime.portrait_composer.compose(
            asset, position, emotion, "sad", self.music_config.tracks, bpm=120,
            harmony_enabled=True,
            harmony_arpeggio_enabled=True,
        )

        self.assertEqual(disabled.bpm, 120)
        self.assertEqual(disabled.harmony_note_count, 0)
        self.assertEqual(disabled.arpeggio_note_count, 0)
        self.assertGreater(len(disabled.notes), 4)
        self.assertGreater(disabled.bass_note_count, 0)
        self.assertEqual(enabled.bpm, 120)
        self.assertEqual(enabled.harmony, ["Am", "F", "C", "G"])
        self.assertEqual(enabled.harmony_note_count, 4)
        self.assertEqual(enabled.arpeggio_note_count, 0)
        harmony = [note for note in enabled.notes if note.voice_role == "harmony"]
        self.assertTrue(all(note.track_id == melody_track.id and note.channel == melody_track.midi_channel for note in harmony))
        self.assertTrue(all(
            note.pitch < next(theme.pitch for theme in enabled.notes if theme.voice_role == "theme" and theme.beat == note.beat)
            for note in harmony
        ))
        ornaments = [note for note in arpeggiated.notes if note.voice_role == "ornament"]
        chord_classes = [
            {9, 0, 4},
            {5, 9, 0},
            {0, 4, 7},
            {7, 11, 2},
        ]
        self.assertEqual(arpeggiated.harmony, ["Am", "F", "C", "G"])
        self.assertEqual(arpeggiated.harmony_note_count, 4)
        self.assertEqual(arpeggiated.arpeggio_note_count, len(ornaments))
        self.assertGreater(arpeggiated.arpeggio_note_count, 0)
        self.assertTrue(all(note.track_id == melody_track.id and note.channel == melody_track.midi_channel for note in ornaments))
        self.assertTrue(all(note.duration_beats <= 0.35 for note in ornaments))
        self.assertTrue(all(note.pitch % 12 in chord_classes[min(int(note.beat // 4), 3)] for note in ornaments))
        self.assertTrue(all(
            note.pitch < max(theme.pitch for theme in arpeggiated.notes if theme.voice_role == "theme" and theme.beat < note.beat)
            for note in ornaments
        ))

    async def test_portrait_harmony_setting_resets_when_a_new_session_starts(self) -> None:
        self.runtime.config = self.runtime.config.model_copy(update={"composition_mode": "portrait"})
        self.assertFalse(
            self.runtime.update_settings(
                {"portrait_harmony_arpeggio_enabled": True}
            )["portrait_harmony_arpeggio_enabled"]
        )
        self.assertTrue(self.runtime.update_settings({"portrait_harmony_enabled": True})["portrait_harmony_enabled"])
        self.assertTrue(
            self.runtime.update_settings(
                {"portrait_harmony_arpeggio_enabled": True}
            )["portrait_harmony_arpeggio_enabled"]
        )
        status = self.runtime.update_settings({"portrait_harmony_enabled": False})
        self.assertFalse(status["portrait_harmony_enabled"])
        self.assertFalse(status["portrait_harmony_arpeggio_enabled"])
        self.assertTrue(self.runtime.update_settings({"portrait_harmony_enabled": True})["portrait_harmony_enabled"])
        self.assertTrue(
            self.runtime.update_settings(
                {"portrait_harmony_arpeggio_enabled": True}
            )["portrait_harmony_arpeggio_enabled"]
        )
        self.runtime.start()
        self.assertFalse(self.runtime.status()["portrait_harmony_enabled"])
        self.assertFalse(self.runtime.status()["portrait_harmony_arpeggio_enabled"])
        await self.runtime.stop()

    async def test_portrait_tempo_profiles_use_a_target_and_smooth_per_phrase(self) -> None:
        arranger = self.runtime.portrait_composer.arranger
        self.assertEqual(arranger.effective_bpm(120, "sad", None), (78, 78))
        self.assertEqual(arranger.effective_bpm(120, "tense", 120), (128, 132))
        self.assertEqual(arranger.effective_bpm(120, "calm", 120), (112, 90))

    async def test_portrait_bass_exists_without_xylophone_harmony(self) -> None:
        asset = self.portrait_library.select("neutral", "loop")
        emotion = EmotionMapper().from_tuple(5, 5, 0.9, 0.1, source="simulator")
        segment = self.runtime.portrait_composer.compose(
            asset,
            self.runtime._portrait_position("loop"),
            emotion,
            "neutral",
            self.music_config.tracks,
            bpm=102,
            harmony_enabled=False,
        )
        bass = next(track for track in self.music_config.tracks if track.role == "bass")
        bass_notes = [note for note in segment.notes if note.track_id == bass.id]
        self.assertGreater(segment.bass_note_count, 0)
        self.assertEqual(segment.harmony_note_count, 0)
        self.assertTrue(bass_notes)
        self.assertTrue(all(note.notochord_eligible for note in bass_notes))

    async def test_invalid_model_revoice_keeps_rule_polyphony(self) -> None:
        self.runtime.config = self.runtime.config.model_copy(update={"composition_mode": "theme"})
        self.runtime.current_theme = self.theme_library.select("ode_to_joy")
        self.runtime.model.model = object()
        self.runtime.model.active_provider = "notochord"
        while self.runtime.form.current().section != "variation":
            self.runtime.form.advance()
        position = self.runtime.form.current()
        original_method = self.runtime.model.ornament_segment

        def invalid_candidate(segment, *_args):
            harmony = next(
                note for note in segment.notes if note.voice_role == "harmony"
            )
            broken = harmony.model_copy(update={"pitch": harmony.pitch + 1})
            notes = [broken if note is harmony else note for note in segment.notes]
            return segment.model_copy(update={
                "source": "hybrid",
                "notochord_modified_count": 1,
                "notes": notes,
            })

        self.runtime.model.ornament_segment = invalid_candidate
        segment = await self.runtime._generate(position)
        self.runtime.model.ornament_segment = original_method

        self.assertEqual(segment.source, "theme")
        self.assertEqual(segment.notochord_modified_count, 0)
        self.assertEqual(self.runtime.fallback_count, 1)
        self.assertIn("invalid polyphonic candidate", self.runtime.generation_error)


class FakeNotochord:
    def __init__(self) -> None:
        self.events = []

    def reset(self) -> None:
        self.events = []

    def query(self, **constraints):
        pitches = list(constraints["include_pitch"])
        return {
            "inst": constraints["next_inst"],
            "pitch": pitches[len(pitches) // 2],
            "time": constraints["next_time"],
            "vel": constraints["min_vel"],
        }

    def feed(self, inst, pitch, time, vel) -> None:
        self.events.append((inst, pitch, time, vel))


class NotochordAdapterTest(unittest.TestCase):
    def test_portrait_assist_only_changes_arranger_owned_notes(self) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        music_config = MusicConfigStore(defaults).active_config
        bass = next(track for track in music_config.tracks if track.role == "bass").model_copy(update={
            "notochord_enabled": True,
            "notochord_mode": "revoice",
            "notochord_rate": 1.0,
            "notochord_instrument": 33,
        })
        model = MelodyModel(Path("/missing/latest.pt"), Path("/missing/model_config.json"), provider="notochord")
        model.model = FakeNotochord()
        model.active_provider = "notochord"
        authored = SegmentNote(beat=0, duration_beats=1, pitch=60, velocity=80, track_id="piano_melody_01", channel=1, voice_role="theme")
        eligible = SegmentNote(beat=0, duration_beats=1, pitch=36, velocity=70, track_id=bass.id, channel=bass.midi_channel, notochord_eligible=True)
        segment = MusicSegment(
            id="portrait-assist", emotion="neutral", previous_emotion="neutral", bpm=96,
            bars=1, beats_per_bar=4, root_note="C", scale="major", source="portrait",
            harmony=["C"], notes=[authored, eligible],
        )

        result = model.assist_portrait_segment(segment, [bass])

        self.assertEqual(
            next(note for note in result.notes if note.track_id == authored.track_id).model_dump(),
            authored.model_dump(),
        )
        modified = next(note for note in result.notes if note.track_id == bass.id)
        self.assertEqual(modified.generated_by, "notochord")
        self.assertEqual(result.notochord_track_counts, {bass.id: 1})

    def test_portrait_drum_fill_uses_reserved_grid_slots(self) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        music_config = MusicConfigStore(defaults).active_config
        drum = next(track for track in music_config.tracks if track.role == "drum").model_copy(update={
            "notochord_enabled": True,
            "notochord_mode": "fill",
            "notochord_rate": 1.0,
            "notochord_instrument": 10,
        })
        model = MelodyModel(Path("/missing/latest.pt"), Path("/missing/model_config.json"), provider="notochord")
        model.model = FakeNotochord()
        model.active_provider = "notochord"
        segment = MusicSegment(
            id="portrait-drum-fill", emotion="joy", previous_emotion="joy", bpm=120,
            bars=1, beats_per_bar=4, root_note="C", scale="major", source="portrait",
        )

        result = model.assist_portrait_segment(segment, [drum])

        notes = [note for note in result.notes if note.track_id == drum.id]
        self.assertTrue(notes)
        self.assertTrue(all(note.pitch in drum.drum_notes.values() for note in notes))
        self.assertTrue(all(note.generated_by == "notochord" for note in notes))

    def test_notochord_candidate_obeys_segment_constraints(self) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        music_config = MusicConfigStore(defaults).active_config
        melody = next(track for track in music_config.tracks if track.role == "melody")
        model = MelodyModel(
            Path("/missing/latest.pt"),
            Path("/missing/model_config.json"),
            provider="notochord",
            notochord_instrument=14,
        )
        model.model = FakeNotochord()
        model.active_provider = "notochord"
        emotion = EmotionMapper().from_tuple(8, 7, 0.85, 0.15, source="simulator")
        candidates = model.generate_candidates(emotion, None, melody, 92, 2, 4, 4)

        self.assertEqual(len(candidates), 2)
        self.assertTrue(CandidateScorer().is_valid(
            candidates[0], melody.id, melody.pitch_range
        ))
        self.assertTrue(all(note.channel == melody.midi_channel for note in candidates[0].notes))

    def test_notochord_only_adds_notes_between_theme_anchors(self) -> None:
        defaults = Path(__file__).resolve().parents[1] / "app" / "config" / "music_defaults.yaml"
        music_config = MusicConfigStore(defaults).active_config
        melody = next(track for track in music_config.tracks if track.role == "melody")
        model = MelodyModel(
            Path("/missing/latest.pt"),
            Path("/missing/model_config.json"),
            provider="notochord",
            notochord_instrument=14,
        )
        model.model = FakeNotochord()
        model.active_provider = "notochord"
        emotion = EmotionMapper().from_tuple(7, 6, 0.85, 0.15, source="simulator")
        anchors = [
            SegmentNote(beat=0, duration_beats=0.5, pitch=60, velocity=80, track_id=melody.id, channel=1),
            SegmentNote(beat=2, duration_beats=0.5, pitch=64, velocity=80, track_id=melody.id, channel=1),
        ]
        segment = MusicSegment(
            id="theme-test",
            emotion="neutral",
            previous_emotion="neutral",
            bpm=84,
            bars=8,
            beats_per_bar=4,
            root_note="C",
            scale="major",
            source="theme",
            notes=anchors,
        )

        result = model.ornament_segment(segment, emotion, melody, 0.5, {0, 2})

        self.assertEqual(result.notes[0].model_dump(), anchors[0].model_dump())
        original = {(note.beat, note.pitch) for note in anchors}
        self.assertTrue(original.issubset({(note.beat, note.pitch) for note in result.notes}))
        self.assertTrue(all(beat not in {0, 2} for beat in result.ornamented_beats))

    def test_notochord_never_changes_tagged_theme_voice(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        defaults = project_root / "backend" / "app" / "config" / "music_defaults.yaml"
        music_config = MusicConfigStore(defaults).active_config
        melody = next(track for track in music_config.tracks if track.role == "melody")
        theme = ThemeLibrary(project_root / "music_library").select("ode_to_joy")
        form = CompositionStateMachine()
        while form.current().section != "variation":
            form.advance()
        emotion = EmotionMapper().from_tuple(8, 7, 0.85, 0.15, source="simulator")
        segment = ThemeComposer().compose(
            theme, form.current(), emotion, "neutral", 92,
            music_config.tracks, 0.65, 0.8,
        )
        original_theme = [
            note.model_dump()
            for note in segment.notes if note.voice_role == "theme"
        ]
        model = MelodyModel(
            Path("/missing/latest.pt"),
            Path("/missing/model_config.json"),
            provider="notochord",
            notochord_instrument=14,
        )
        model.model = FakeNotochord()
        model.active_provider = "notochord"

        result = model.ornament_segment(
            segment, emotion, melody, 0.8, set(theme.immutable_beats)
        )

        self.assertEqual(
            original_theme,
            [note.model_dump() for note in result.notes if note.voice_role == "theme"],
        )
        self.assertGreater(result.notochord_modified_count, 0)
        self.assertTrue(all(
            note.generated_by == "notochord"
            for note in result.notes
            if note.beat in result.ornamented_beats
            or (note.voice_role in {"harmony", "ornament"} and note.generated_by == "notochord")
        ))

if __name__ == "__main__":
    unittest.main()
