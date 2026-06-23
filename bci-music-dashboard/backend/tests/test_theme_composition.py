from pathlib import Path
import unittest

from app.bci.emotion_mapper import EmotionMapper
from app.music.config_loader import MusicConfigStore
from app.music.generation.form import CompositionStateMachine
from app.music.generation.theme_composer import ThemeComposer
from app.music.generation.theme_library import ThemeLibrary
from app.music.generation.scoring import CandidateScorer


class ThemeCompositionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[2]
        defaults = project_root / "backend" / "app" / "config" / "music_defaults.yaml"
        cls.music_config = MusicConfigStore(defaults).active_config
        cls.library = ThemeLibrary(project_root / "music_library")
        cls.theme = cls.library.select("ode_to_joy")

    def test_public_domain_theme_loads_with_arrangement(self) -> None:
        self.assertEqual(self.theme.bars, 8)
        self.assertEqual(len(self.theme.harmony), 8)
        self.assertEqual(self.theme.license["composition"], "public_domain")
        self.assertTrue((self.theme.path / "LICENSE.md").exists())

    def test_form_fits_target_duration_without_cutting_phrases(self) -> None:
        form = CompositionStateMachine()
        form.configure(84, 240)
        sections = [section for section, _ in form.positions]
        self.assertEqual(sections[0], "intro")
        self.assertEqual(sections[-1], "coda")
        self.assertEqual(sections.count("theme"), 2)
        self.assertEqual(sections.count("return"), 2)
        duration = len(sections) * 8 * 4 * 60 / 84
        self.assertGreaterEqual(duration, 180)
        self.assertLessEqual(duration, 300)

    def test_theme_phrase_preserves_anchors_and_adds_arrangement_tracks(self) -> None:
        form = CompositionStateMachine()
        form.configure(84, 240)
        while form.current().section != "theme":
            form.advance()
        emotion = EmotionMapper().from_tuple(7, 5, 0.9, 0.1, source="simulator")
        segment = ThemeComposer().compose(
            self.theme,
            form.current(),
            emotion,
            "neutral",
            84,
            self.music_config.tracks,
            0.65,
            0.35,
        )
        melody = [
            note for note in segment.notes
            if note.track_id == "piano_melody_01" and note.voice_role == "theme"
        ]
        melody_beats = {note.beat for note in melody}
        anchor_hits = len(self.theme.anchors & melody_beats) / len(self.theme.anchors)
        self.assertGreaterEqual(anchor_hits, 0.9)
        self.assertGreaterEqual(segment.theme_similarity, 0.9)
        self.assertTrue(any(note.track_id == "chord_pad_01" for note in segment.notes))
        self.assertTrue(any(note.track_id == "bass_01" for note in segment.notes))
        source_by_beat = {note.beat: note.duration_beats for note in self.theme.notes}
        self.assertTrue(all(
            note.duration_beats < source_by_beat[note.beat]
            for note in melody
        ))

    def test_polyphony_one_preserves_single_theme_voice(self) -> None:
        tracks = [track.model_copy(deep=True) for track in self.music_config.tracks]
        melody_track = next(track for track in tracks if track.role == "melody")
        melody_track.polyphony = 1
        segment = self._compose_section("theme", tracks)
        notes = [note for note in segment.notes if note.track_id == melody_track.id]
        self.assertEqual(segment.actual_max_voices, 1)
        self.assertEqual(segment.harmony_note_count, 0)
        self.assertTrue(all(note.voice_role == "theme" for note in notes))

    def test_polyphony_two_adds_only_lower_channel_one_harmony(self) -> None:
        tracks = [track.model_copy(deep=True) for track in self.music_config.tracks]
        melody_track = next(track for track in tracks if track.role == "melody")
        melody_track.polyphony = 2
        segment = self._compose_section("theme", tracks)
        notes = [note for note in segment.notes if note.track_id == melody_track.id]
        by_beat = {}
        for note in notes:
            by_beat.setdefault(note.beat, []).append(note)
        self.assertEqual(segment.actual_max_voices, 2)
        self.assertGreater(segment.harmony_note_count, 0)
        self.assertTrue(all(note.channel == 1 for note in notes))
        self.assertTrue(all(len(onset) <= 2 for onset in by_beat.values()))
        self.assertTrue(any(len(onset) == 1 for onset in by_beat.values()))
        for onset in by_beat.values():
            theme = next((note for note in onset if note.voice_role == "theme"), None)
            if theme:
                self.assertTrue(all(
                    note.pitch < theme.pitch
                    for note in onset if note.voice_role == "harmony"
                ))

    def test_arpeggio_can_be_disabled_without_affecting_theme_voicing(self) -> None:
        tracks = [track.model_copy(deep=True) for track in self.music_config.tracks]
        melody_track = next(track for track in tracks if track.role == "melody")
        melody_track.arpeggio_enabled = False
        segment = self._compose_section("variation", tracks)
        notes = [note for note in segment.notes if note.track_id == melody_track.id]

        self.assertEqual(segment.arpeggio_note_count, 0)
        self.assertFalse(any(note.voice_role == "ornament" for note in notes))
        self.assertGreater(segment.harmony_note_count, 0)

    def test_arpeggio_adds_channel_one_ornaments_without_covering_theme(self) -> None:
        segment = self._compose_section("climax")
        melody_track = next(track for track in self.music_config.tracks if track.role == "melody")
        notes = [note for note in segment.notes if note.track_id == melody_track.id]
        ornaments = [note for note in notes if note.voice_role == "ornament"]
        theme_beats = {round(note.beat, 3) for note in notes if note.voice_role == "theme"}

        self.assertGreater(segment.arpeggio_note_count, 0)
        self.assertEqual(segment.arpeggio_note_count, len(ornaments))
        self.assertTrue(all(note.channel == 1 for note in ornaments))
        self.assertTrue(all(note.generated_by == "rule" for note in ornaments))
        self.assertTrue(all(note.duration_beats <= 0.5 for note in ornaments))
        self.assertFalse(any(round(note.beat, 3) in theme_beats for note in ornaments))
        self.assertTrue(CandidateScorer().is_valid(
            segment, melody_track.id, melody_track.pitch_range
        ))

    def test_climax_uses_more_three_voice_onsets_than_intro(self) -> None:
        intro = self._compose_section("intro")
        climax = self._compose_section("climax")

        def triple_count(segment):
            onsets = {}
            for note in segment.notes:
                if note.track_id == "piano_melody_01":
                    onsets.setdefault(note.beat, set()).add(note.pitch)
            return sum(len(pitches) == 3 for pitches in onsets.values())

        self.assertEqual(climax.actual_max_voices, 3)
        self.assertGreater(triple_count(climax), triple_count(intro))
        melody = next(
            track for track in self.music_config.tracks if track.role == "melody"
        )
        self.assertTrue(CandidateScorer().is_valid(
            climax, melody.id, melody.pitch_range
        ))

    def _compose_section(self, section, tracks=None):
        form = CompositionStateMachine()
        form.configure(84, 240)
        while form.current().section != section:
            form.advance()
        emotion = EmotionMapper().from_tuple(
            7, 7, 0.9, 0.1, source="simulator"
        )
        return ThemeComposer().compose(
            self.theme,
            form.current(),
            emotion,
            "neutral",
            84,
            tracks or self.music_config.tracks,
            0.65,
            0.35,
        )


if __name__ == "__main__":
    unittest.main()
