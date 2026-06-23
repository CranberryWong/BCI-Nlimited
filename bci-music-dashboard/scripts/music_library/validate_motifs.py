from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "backend"))

from app.music.generation.motif_library import MotifLibrary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate motif MIDI/YAML pairs.")
    parser.add_argument("--root", type=Path, default=PROJECT / "music_library")
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument(
        "--ignore-unpaired-midi",
        action="store_true",
        help="Ignore raw/source MIDI files that do not have YAML pairs. Useful for fast local debugging.",
    )
    args = parser.parse_args()

    library = MotifLibrary(args.root)
    errors = list(library.errors)
    yaml_files = sorted((args.root / "motifs").glob("*/*.yaml"))
    for yaml_path in yaml_files:
        midi_path = yaml_path.with_suffix(".mid")
        if not midi_path.exists():
            errors.append(f"{yaml_path}: missing MIDI pair")
    for midi_path in sorted((args.root / "motifs").glob("*/*.mid")):
        yaml_path = midi_path.with_suffix(".yaml")
        if not yaml_path.exists() and not args.ignore_unpaired_midi:
            errors.append(f"{midi_path}: missing YAML pair")
    if args.require_approved and not library.list(approved_only=True):
        errors.append("no approved motifs available")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"Validated {len(library.motifs)} motifs ({len(library.list(approved_only=True))} approved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
