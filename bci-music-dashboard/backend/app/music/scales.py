from __future__ import annotations

import random


ROOTS = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "pentatonic": (0, 2, 4, 7, 9),
    "chromatic": tuple(range(12)),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
}


def resolve_scale(track_scale: str, profile_scale: str, global_scale: str, label: str) -> str:
    for candidate in (track_scale, profile_scale, global_scale):
        if candidate != "auto" and candidate in SCALES:
            return candidate
    return "minor" if label in {"sad", "tense"} else "major"


def root_pc(note: str, fallback: str = "C") -> int:
    return ROOTS.get(note if note != "auto" else fallback, ROOTS["C"])


def scale_notes(root: int, scale: str, low: int, high: int) -> list[int]:
    degrees = SCALES.get(scale, SCALES["major"])
    return [pitch for pitch in range(low, high + 1) if (pitch - root) % 12 in degrees]


def choose_quantized(root: int, scale: str, low: int, high: int, position: float, randomness: float) -> int:
    notes = scale_notes(root, scale, low, high) or list(range(low, high + 1))
    target_index = round(max(0.0, min(1.0, position)) * (len(notes) - 1))
    wander = max(0, round(randomness * max(1, len(notes) / 5)))
    return notes[max(0, min(len(notes) - 1, target_index + random.randint(-wander, wander)))]


def enumerate_scale_sequence(root_note: str, scale: str, low: int, high: int) -> list[int]:
    return scale_notes(root_pc(root_note), scale, low, high)
