from __future__ import annotations

import argparse
import hashlib
import random

from common import EMOTIONS, PROCESSED_DIR, TRAINING_DIR, write_jsonl
from app.music.generation.tokens import encode_notes
from app.music.schemas import SegmentNote
from midi_data import parse_melody


def split_for(path) -> str:
    value = int(hashlib.sha256(str(path).encode()).hexdigest()[:8], 16) % 10
    return "train" if value < 8 else "validation" if value == 8 else "test"


def segment_notes(notes: list[SegmentNote], start: float, transpose: int) -> list[SegmentNote]:
    result = []
    for note in notes:
        if start <= note.beat < start + 16:
            result.append(note.model_copy(update={
                "beat": round((note.beat - start) * 4) / 4,
                "duration_beats": max(0.25, round(note.duration_beats * 4) / 4),
                "pitch": note.pitch + transpose,
                "track_id": "piano_melody_01",
                "channel": 1,
            }))
    return [note for note in result if 21 <= note.pitch <= 108 and note.beat + note.duration_beats <= 16]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare four-bar token sequences.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)
    rows = {"train": [], "validation": [], "test": []}
    for emotion in EMOTIONS:
        files = sorted((TRAINING_DIR / emotion).glob("*.mid")) + sorted((TRAINING_DIR / emotion).glob("*.midi"))
        for path in files:
            parsed = parse_melody(path)
            maximum = max(note.beat + note.duration_beats for note in parsed.notes)
            for start in range(0, int(maximum), 16):
                for transpose in (-2, 0, 2):
                    notes = segment_notes(parsed.notes, start, transpose)
                    if len(notes) < 8:
                        continue
                    row = {
                        "emotion": emotion,
                        "previous_emotion": emotion,
                        "bpm": parsed.bpm,
                        "source": str(path.relative_to(TRAINING_DIR)),
                        "tokens": encode_notes(notes, emotion, emotion, parsed.bpm),
                    }
                    rows[split_for(path)].append(row)
    for split, items in rows.items():
        write_jsonl(PROCESSED_DIR / f"{split}.jsonl", items)
        print(f"{split}: {len(items)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
