from __future__ import annotations

import argparse
from pathlib import Path

from common import EMOTIONS, TRAINING_DIR
from midi_data import parse_melody


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate five-emotion MIDI training folders.")
    parser.add_argument("--root", default=str(TRAINING_DIR))
    args = parser.parse_args()
    failures = 0
    total = 0
    root = Path(args.root)
    for emotion in EMOTIONS:
        files = sorted((root / emotion).glob("*.mid")) + sorted((root / emotion).glob("*.midi"))
        total += len(files)
        print(f"{emotion}: {len(files)} file(s)")
        if len(files) < 20:
            print(f"  WARNING: fewer than 20 source files for {emotion}")
        for path in files:
            try:
                parsed = parse_melody(path)
                pitches = [note.pitch for note in parsed.notes]
                print(f"  OK {path.name}: {len(parsed.notes)} notes, {min(pitches)}-{max(pitches)}, {parsed.bpm} BPM")
            except Exception as exc:
                failures += 1
                print(f"  ERROR {path.name}: {exc}")
    if total == 0:
        print("WARNING: no MIDI files found; rule mode remains available.")
    print(f"validated={total} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
