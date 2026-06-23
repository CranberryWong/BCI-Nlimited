from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]


def title_from_stem(stem: str) -> str:
    parts = stem.split("_")
    if len(parts) > 1 and parts[-1].isdigit():
        parts = parts[:-1]
    return " ".join(part.capitalize() for part in parts) or stem


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze every raw MIDI in a motif emotion folder.")
    parser.add_argument("folder", type=Path, help="Example: music_library/motifs/joy")
    parser.add_argument("--emotion", required=True, choices=("calm", "joy", "neutral", "sad", "tense"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--strict-single-melody", action="store_true")
    args = parser.parse_args()

    analyzer = PROJECT / "scripts" / "music_library" / "analyze_motif.py"
    midi_files = sorted(
        path for path in args.folder.glob("*.mid")
        if not path.stem.endswith(("_melody", "_debug"))
    )
    if not midi_files:
        print(f"No raw MIDI files found in {args.folder}")
        return 0

    failures = 0
    for midi_path in midi_files:
        output = midi_path.with_name(f"{midi_path.stem}_melody.yaml")
        if output.exists() and not args.overwrite:
            print(f"skip existing {output}")
            continue
        command = [
            sys.executable,
            str(analyzer),
            str(midi_path),
            "--emotion",
            args.emotion,
            "--title",
            title_from_stem(midi_path.stem),
        ]
        if args.strict_single_melody:
            command.append("--strict-single-melody")
        result = subprocess.run(command, cwd=PROJECT)
        if result.returncode != 0:
            failures += 1
    if failures:
        print(f"Completed with {failures} failures")
        return 1
    print(f"Analyzed {len(midi_files)} MIDI files in {args.folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
