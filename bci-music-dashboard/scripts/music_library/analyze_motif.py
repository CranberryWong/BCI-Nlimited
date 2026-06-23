from __future__ import annotations

import argparse
from math import ceil
from pathlib import Path
import sys
from typing import Any

import mido
import yaml

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "backend"))

from app.music.generation.motif_library import MotifValidationError, read_single_melody_midi  # noqa: E402


PORTRAITS: dict[str, dict[str, str]] = {
    "joy": {
        "rhythm_profile": "buoyant",
        "articulation": "light_staccato",
        "arpeggio_shape": "upward_sparkle",
        "harmony_color": "bright_open",
        "register_motion": "rising",
        "texture_density": "high",
        "transition_style": "lift",
    },
    "calm": {
        "rhythm_profile": "breathing",
        "articulation": "soft_legato",
        "arpeggio_shape": "gentle_wave",
        "harmony_color": "open_warm",
        "register_motion": "floating",
        "texture_density": "low",
        "transition_style": "dissolve",
    },
    "neutral": {
        "rhythm_profile": "regular",
        "articulation": "balanced",
        "arpeggio_shape": "simple_outline",
        "harmony_color": "stable",
        "register_motion": "centered",
        "texture_density": "medium",
        "transition_style": "plain",
    },
    "sad": {
        "rhythm_profile": "sparse_breathing",
        "articulation": "soft_legato",
        "arpeggio_shape": "falling_fragments",
        "harmony_color": "minor_warm",
        "register_motion": "descending",
        "texture_density": "low",
        "transition_style": "warmth",
    },
    "tense": {
        "rhythm_profile": "syncopated",
        "articulation": "short_accented",
        "arpeggio_shape": "jagged",
        "harmony_color": "controlled_tension",
        "register_motion": "wide",
        "texture_density": "high",
        "transition_style": "grounding",
    },
}


def collect_midi_notes(path: Path) -> tuple[mido.MidiFile, list[tuple[int, int, int, int]]]:
    midi = mido.MidiFile(path)
    active: dict[tuple[int, int], tuple[int, int]] = {}
    notes: list[tuple[int, int, int, int]] = []
    absolute = 0
    for message in mido.merge_tracks(midi.tracks):
        absolute += message.time
        if message.type == "note_on" and message.velocity > 0 and not getattr(message, "is_meta", False):
            active[(message.channel, message.note)] = (absolute, message.velocity)
        elif message.type in {"note_off", "note_on"} and getattr(message, "note", None) is not None:
            started = active.pop((message.channel, message.note), None)
            if started:
                start_tick, velocity = started
                if absolute > start_tick:
                    notes.append((start_tick, absolute, message.note, velocity))
    return midi, sorted(notes, key=lambda item: (item[0], item[2]))


def extract_monophonic_melody(source: Path, output: Path, strategy: str) -> None:
    midi, source_notes = collect_midi_notes(source)
    if not source_notes:
        raise MotifValidationError(f"MIDI contains no notes: {source}")

    min_duration_ticks = max(1, int(round(midi.ticks_per_beat * 0.125)))
    selected: list[tuple[int, int, int, int]] = []
    by_start: dict[int, list[tuple[int, int, int, int]]] = {}
    for note in source_notes:
        by_start.setdefault(note[0], []).append(note)

    for start_tick in sorted(by_start):
        candidates = by_start[start_tick]
        chosen = max(candidates, key=lambda item: item[2]) if strategy == "highest" else min(candidates, key=lambda item: item[2])
        if selected and start_tick < selected[-1][1]:
            previous = selected[-1]
            selected[-1] = (previous[0], start_tick, previous[2], previous[3])
            if selected[-1][1] - selected[-1][0] < min_duration_ticks:
                selected.pop()
        if chosen[1] - chosen[0] >= min_duration_ticks:
            selected.append(chosen)

    clean_midi = mido.MidiFile(ticks_per_beat=midi.ticks_per_beat)
    track = mido.MidiTrack()
    clean_midi.tracks.append(track)
    for message in mido.merge_tracks(midi.tracks):
        if message.type in {"time_signature", "set_tempo"}:
            copied = message.copy(time=0)
            track.append(copied)

    events: list[tuple[int, int, mido.Message]] = []
    for index, (start_tick, end_tick, pitch, velocity) in enumerate(selected):
        if end_tick <= start_tick:
            continue
        events.append((start_tick, 1, mido.Message("note_on", note=pitch, velocity=velocity, channel=0)))
        events.append((end_tick, 0, mido.Message("note_off", note=pitch, velocity=0, channel=0)))
    last_tick = 0
    for tick, _, message in sorted(events, key=lambda item: (item[0], item[1])):
        message.time = max(0, tick - last_tick)
        track.append(message)
        last_tick = tick
    output.parent.mkdir(parents=True, exist_ok=True)
    clean_midi.save(output)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate draft motif YAML from a MIDI file.")
    parser.add_argument("midi", type=Path)
    parser.add_argument("--emotion", required=True, choices=sorted(PORTRAITS))
    parser.add_argument("--title", required=True)
    parser.add_argument("--id", dest="motif_id")
    parser.add_argument("--home-key", default="C")
    parser.add_argument("--mode", default=None)
    parser.add_argument("--tempo", type=int, default=None)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--extract-melody",
        choices=("highest", "lowest"),
        help="Create a monophonic MIDI from a polyphonic source before analysis. Defaults to highest when needed.",
    )
    parser.add_argument(
        "--strict-single-melody",
        action="store_true",
        help="Fail instead of auto-extracting when the source MIDI contains chords, overlaps, bass, or accompaniment.",
    )
    parser.add_argument(
        "--clean-midi",
        type=Path,
        help="Output path for --extract-melody. Defaults to '<stem>_melody.mid'.",
    )
    args = parser.parse_args()

    midi_path = args.midi
    extraction_strategy = args.extract_melody or "highest"
    try:
        notes, meter = read_single_melody_midi(midi_path)
    except MotifValidationError as exc:
        if args.strict_single_melody:
            raise SystemExit(
                f"{exc}\n"
                "This usually means the MIDI contains chords, overlapping notes, bass, or accompaniment. "
                "Export a single melody line, or rerun without --strict-single-melody to auto-extract a top-line motif."
            ) from exc
        clean_midi = args.clean_midi or args.midi.with_name(f"{args.midi.stem}_melody.mid")
        print(
            f"{exc}\n"
            f"Auto-extracting {extraction_strategy} melody to {clean_midi}",
            file=sys.stderr,
        )
        extract_monophonic_melody(args.midi, clean_midi, extraction_strategy)
        midi_path = clean_midi
        notes, meter = read_single_melody_midi(midi_path)

    beats_per_bar = int(meter.split("/")[0])
    total_beats = max(note.beat + note.duration_beats for note in notes)
    bars = max(1, ceil(total_beats / beats_per_bar))
    motif_id = args.motif_id or midi_path.stem
    output = args.output or midi_path.with_suffix(".yaml")
    strong = {
        round(note.beat, 3)
        for note in notes
        if abs(note.beat % beats_per_bar) < 0.01
        or abs(note.beat % beats_per_bar - 2) < 0.01
        or note.duration_beats >= 1.0
    }
    anchors = sorted(strong)[: max(1, min(8, bars * 2))]
    if notes[-1].duration_beats >= 0.75:
        anchors = sorted(set(anchors + [round(notes[-1].beat, 3)]))
    immutable = sorted(set(anchors[: max(1, min(4, len(anchors)))] + [round(notes[-1].beat, 3)]))
    mutable = [
        round(note.beat, 3)
        for note in notes
        if round(note.beat, 3) not in immutable
    ]
    payload: dict[str, Any] = {
        "id": motif_id,
        "title": args.title,
        "source_type": "lyria_generated",
        "emotion": args.emotion,
        "license": {
            "composition": "generated_or_self_curated",
            "model": "Google Lyria",
            "generated_date": "TODO",
            "midi_source": "manually_transcribed_or_corrected",
            "editor": "TODO",
        },
        "meter": meter,
        "bars": bars,
        "home_key": args.home_key,
        "mode": args.mode or ("yu" if args.emotion == "sad" else "jue" if args.emotion == "tense" else "gong"),
        "tempo_hint": args.tempo or {"joy": 108, "calm": 68, "neutral": 84, "sad": 60, "tense": 120}[args.emotion],
        "pitch_range": [min(note.pitch for note in notes), max(note.pitch for note in notes)],
        "phrases": [{
            "id": "A",
            "bars": [1, bars],
            "role": "motif",
            "anchors": anchors,
            "cadence": "authentic" if notes[-1].duration_beats >= 0.75 else "open",
        }],
        "anchors": anchors,
        "immutable_beats": immutable,
        "mutable_beats": mutable,
        "harmony": [{"bars": [bar, bar], "chord": "I"} for bar in range(1, bars + 1)],
        "variation_allowed": {
            "transpose": [-2, 2],
            "octave_shift": [-12, 12],
            "rhythm_expand": True,
            "rhythm_compress": True,
            "ornament": True,
            "delete_mutable_notes": True,
            "repeat_motif": True,
            "arpeggiate": True,
            "notochord_fill": True,
        },
        "portrait_behavior": PORTRAITS[args.emotion],
        "orchestration": {
            "melody": "xylophone",
            "harmony": "pad",
            "bass": "synth_bass",
            "percussion_profile": "light_pulse" if args.emotion in {"joy", "neutral"} else "sparse",
            "cymbal_profile": "phrase_boundary_only",
        },
        "quality": {
            "approved": False,
            "notes": "draft generated by analyze_motif.py; human review required",
        },
    }
    output.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
