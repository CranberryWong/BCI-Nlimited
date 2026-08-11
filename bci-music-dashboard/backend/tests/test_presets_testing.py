import asyncio
from pathlib import Path
import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.music.config_loader import MusicConfigStore
from app.music.generation.model import MelodyModel
from app.music.generation.presets_testing import PresetsTestingLibrary, PresetsTestingRuntime
from app.music.schemas import MusicSegment, SegmentNote


class BrokenAssistant:
    def assist_portrait_segment(self, _segment, _tracks):
        raise TimeoutError("simulated timeout")


class PresetsTestingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        defaults = cls.root / "backend" / "app" / "config" / "music_defaults.yaml"
        cls.tracks = MusicConfigStore(defaults).active_config.tracks
        cls.library = PresetsTestingLibrary(cls.root / "music_library")

    def _runtime(self, model=None):
        return PresetsTestingRuntime(self.library, self.tracks, model or MelodyModel(Path("/missing/model"), Path("/missing/config")), lambda _event: None, lambda: None, self._broadcast)

    async def _broadcast(self, _message):
        pass

    @staticmethod
    def _emotion(label="calm"):
        values = {"calm": (8, 3), "joy": (8, 8), "tense": (2, 8), "sad": (2, 2), "neutral": (5, 5)}
        return EmotionMapper().from_tuple(*values[label], .9, .1, source="simulator")

    def test_selects_only_the_exact_fifty_original_sources(self):
        self.assertEqual(len(self.library.sources), 50)
        self.assertTrue(all(path.name.endswith(".mid") and "_melody" not in path.name and "_performance" not in path.name for path in self.library.sources))
        piece = self.library.choose("joy", __import__("random").Random(3))
        self.assertEqual(piece.emotion, "joy")
        self.assertGreater(piece.bpm, 0)
        self.assertTrue(piece.phrase_starts)

    def test_windows_are_continuous_and_mother_source_never_switches(self):
        runtime = self._runtime()
        runtime.piece = self.library.choose("calm", runtime.rng)
        first = runtime.compose_window(self._emotion("calm"))
        source = runtime.piece.id
        runtime.cursor = (runtime.cursor + runtime.WINDOW_BARS * runtime.piece.beats_per_bar) % (runtime.piece.bars * runtime.piece.beats_per_bar)
        second = runtime.compose_window(self._emotion("joy"))
        self.assertEqual(runtime.piece.id, source)
        self.assertNotEqual(first.phrase_id, second.phrase_id)
        self.assertEqual(second.portrait_asset_id, source)

    def test_anchor_notes_are_immutable_and_tempo_steps_are_bounded(self):
        runtime = self._runtime()
        runtime.piece = self.library.choose("neutral", runtime.rng)
        runtime.current_bpm = runtime.piece.bpm
        segment = runtime.compose_window(self._emotion("tense"))
        melody = [note for note in segment.notes if note.voice_role == "theme"]
        raw_by_relative = {
            (round((note.beat - runtime.cursor) % (runtime.piece.bars * runtime.piece.beats_per_bar), 3), note.pitch): note
            for note in runtime.piece.notes if note.beat in runtime.piece.anchor_beats
        }
        for note in melody:
            raw = raw_by_relative.get((round(note.beat, 3), note.pitch))
            if raw:
                self.assertEqual(note.velocity, raw.velocity)
        self.assertLessEqual(abs(segment.bpm - runtime.piece.bpm), runtime.MAX_BPM_STEP)
        self.assertTrue(all(note.generated_by == "rule" and not note.notochord_eligible for note in melody))

    def test_percussion_follows_melody_onsets_and_stays_legal(self):
        runtime = self._runtime()
        runtime.piece = self.library.choose("joy", runtime.rng)
        segment = runtime.compose_window(self._emotion("joy"))
        melody_onsets = {note.beat for note in segment.notes if note.voice_role == "theme"}
        tracks = {track.id: track for track in self.tracks}
        percussion = [note for note in segment.notes if tracks[note.track_id].role in {"drum", "cymbal"}]
        self.assertTrue(percussion)
        self.assertTrue(all(note.beat in melody_onsets for note in percussion))
        self.assertTrue(all(note.pitch in tracks[note.track_id].drum_notes.values() for note in percussion))

    def test_notochord_timeout_uses_rule_fallback(self):
        runtime = self._runtime(BrokenAssistant())
        runtime.piece = self.library.choose("sad", runtime.rng)
        segment = runtime.compose_window(self._emotion("sad"))
        self.assertEqual(runtime.fallback_count, 1)
        self.assertIn("fallback", runtime.generation_error)
        self.assertEqual(runtime.notochord_percussion_count, 0)
        self.assertTrue(all(note.generated_by == "rule" for note in segment.notes))

    def test_scheduler_releases_every_note_and_stop_cancels_pending_tasks(self):
        events = []
        runtime = PresetsTestingRuntime(self.library, self.tracks, MelodyModel(Path("/missing/model"), Path("/missing/config")), events.append, lambda: None, self._broadcast)
        melody = next(track for track in self.tracks if track.role == "melody")
        segment = MusicSegment(
            id="release-test", emotion="neutral", previous_emotion="neutral", bpm=220,
            bars=1, beats_per_bar=1, source="portrait", form_section="theme",
            notes=[SegmentNote(beat=0, duration_beats=.01, pitch=60, velocity=70, track_id=melody.id, channel=melody.midi_channel)],
        )

        async def verify():
            await asyncio.gather(*runtime._schedule(segment))
            self.assertEqual([event.type for event in events], ["note_on", "note_off"])
            pending = runtime._schedule(segment)
            await runtime.stop()
            self.assertTrue(all(task.cancelled() or task.done() for task in pending))

        asyncio.run(verify())
