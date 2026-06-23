from __future__ import annotations

import argparse
import json

from common import CHECKPOINT_DIR, EMOTIONS, PROCESSED_DIR, load_jsonl
from app.music.generation.tokens import decode_tokens
from app.music.scales import SCALES
from midi_data import write_midi


def metrics(notes, scale="gong"):
    intervals = [abs(right.pitch - left.pitch) for left, right in zip(notes, notes[1:])]
    degrees = SCALES[scale]
    return {
        "notes": len(notes),
        "in_scale_ratio": sum(note.pitch % 12 in degrees for note in notes) / max(1, len(notes)),
        "large_leap_ratio": sum(value > 7 for value in intervals) / max(1, len(intervals)),
        "pitch_range": (max((note.pitch for note in notes), default=0) - min((note.pitch for note in notes), default=0)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate tokenized melody data and export examples.")
    parser.add_argument("--split", default="validation")
    args = parser.parse_args()
    rows = load_jsonl(PROCESSED_DIR / f"{args.split}.jsonl")
    report = {}
    sample_dir = CHECKPOINT_DIR / "evaluation_samples"
    for emotion in EMOTIONS:
        row = next((item for item in rows if item["emotion"] == emotion), None)
        if not row:
            report[emotion] = {"warning": "no sample"}
            continue
        notes = decode_tokens(row["tokens"][4:], "piano_melody_01", 1)
        report[emotion] = metrics(notes)
        write_midi(sample_dir / f"{emotion}.mid", notes, row["bpm"])
    output = CHECKPOINT_DIR / "evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
