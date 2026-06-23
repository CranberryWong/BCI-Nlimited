from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

import mido
import yaml

from app.music.generation.motif_library import MotifLibrary


PROJECT = Path(__file__).resolve().parents[2]


def write_midi(path: Path, overlap: bool = False) -> None:
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    events = [
        (0, "note_on", 64, 82),
        (480, "note_off", 64, 0),
        (480, "note_on", 67, 80),
        (1440 if overlap else 960, "note_off", 67, 0),
        (960, "note_on", 69, 78),
        (1440, "note_off", 69, 0),
        (1920, "note_on", 72, 84),
        (2880, "note_off", 72, 0),
    ]
    events.sort(key=lambda item: (item[0], 0 if item[1] == "note_off" else 1))
    cursor = 0
    for tick, kind, pitch, velocity in events:
        track.append(mido.Message(kind, note=pitch, velocity=velocity, channel=0, time=tick - cursor))
        cursor = tick
    midi.save(path)


def write_yaml(path: Path, approved: bool) -> None:
    payload = {
        "id": path.stem,
        "title": "Test Motif",
        "source_type": "unit_test",
        "emotion": "joy",
        "license": {"composition": "test", "midi_source": "self_transcribed"},
        "meter": "4/4",
        "bars": 2,
        "home_key": "C",
        "mode": "major",
        "tempo_hint": 108,
        "pitch_range": [64, 72],
        "phrases": [{"id": "A", "bars": [1, 2], "role": "motif", "anchors": [0], "cadence": "authentic"}],
        "anchors": [0],
        "immutable_beats": [0],
        "mutable_beats": [1, 2],
        "harmony": [{"bars": [1, 2], "chord": "I"}],
        "variation_allowed": {"transpose": [-2, 2], "octave_shift": [-12, 12], "delete_mutable_notes": True},
        "portrait_behavior": {"rhythm_profile": "buoyant", "transition_style": "lift"},
        "orchestration": {"melody": "xylophone", "percussion_profile": "light_pulse"},
        "quality": {"approved": approved},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


class MotifLibraryTest(unittest.TestCase):
    def test_analyze_motif_generates_draft_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            midi_path = Path(tmp) / "joy_001.mid"
            write_midi(midi_path)
            subprocess.run(
                [
                    "python",
                    str(PROJECT / "scripts/music_library/analyze_motif.py"),
                    str(midi_path),
                    "--emotion",
                    "joy",
                    "--title",
                    "Bright Test",
                ],
                cwd=PROJECT,
                check=True,
                capture_output=True,
                text=True,
            )
            data = yaml.safe_load(midi_path.with_suffix(".yaml").read_text(encoding="utf-8"))
            self.assertEqual(data["emotion"], "joy")
            self.assertFalse(data["quality"]["approved"])
            self.assertIn("portrait_behavior", data)

    def test_library_indexes_only_approved_motifs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            joy = root / "motifs" / "joy"
            joy.mkdir(parents=True)
            write_midi(joy / "approved.mid")
            write_yaml(joy / "approved.yaml", approved=True)
            write_midi(joy / "draft.mid")
            write_yaml(joy / "draft.yaml", approved=False)

            library = MotifLibrary(root)

            self.assertEqual(len(library.motifs), 2)
            self.assertEqual(len(library.list(approved_only=True)), 1)
            self.assertEqual(library.select("joy").id, "approved")

    def test_library_rejects_overlapping_melody(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            joy = root / "motifs" / "joy"
            joy.mkdir(parents=True)
            write_midi(joy / "bad.mid", overlap=True)
            write_yaml(joy / "bad.yaml", approved=True)

            library = MotifLibrary(root)

            self.assertFalse(library.motifs)
            self.assertTrue(any("non-overlapping melody" in error for error in library.errors))


if __name__ == "__main__":
    unittest.main()
