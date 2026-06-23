from __future__ import annotations

import argparse
from math import ceil
from pathlib import Path
import sys
from typing import Any

import mido
import yaml

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "backend"))

from app.music.generation.motif_library import MotifNote, read_single_melody_midi  # noqa: E402
from scripts.music_library.analyze_motif import PORTRAITS  # noqa: E402


DEFAULT_TEMPO = {
    "joy": 108,
    "calm": 68,
    "neutral": 84,
    "sad": 60,
    "tense": 120,
}


def note_weight(note: MotifNote) -> float:
    duration_bonus = min(note.duration_beats, 1.5) * 0.25
    register_bonus = 0.25 if 55 <= note.pitch <= 86 else 0.0
    return 1.0 + duration_bonus + register_bonus


def choose_window(notes: list[MotifNote], bars: int, beats_per_bar: int) -> float:
    total_beats = max(note.beat + note.duration_beats for note in notes)
    window_beats = bars * beats_per_bar
    if total_beats <= window_beats:
        return 0.0

    best_start = 0.0
    best_score = -1.0
    max_bar = max(0, ceil((total_beats - window_beats) / beats_per_bar))
    for bar in range(max_bar + 1):
        start = bar * beats_per_bar
        end = start + window_beats
        selected = [note for note in notes if start <= note.beat < end]
        if len(selected) < max(4, bars):
            continue
        score = sum(note_weight(note) for note in selected)
        # Avoid picking a hyperactive transcription burst when a calmer window is close in score.
        if len(selected) > bars * 12:
            score *= 0.75
        if score > best_score:
            best_score = score
            best_start = float(start)
    return best_start


def clipped_notes(notes: list[MotifNote], start: float, bars: int, beats_per_bar: int) -> list[MotifNote]:
    end = start + bars * beats_per_bar
    clipped: list[MotifNote] = []
    for note in notes:
        if not start <= note.beat < end:
            continue
        new_beat = round(note.beat - start, 3)
        new_duration = min(note.duration_beats, end - note.beat)
        if new_duration >= 0.125:
            clipped.append(MotifNote(new_beat, round(new_duration, 3), note.pitch, note.velocity))
    return clipped


def write_midi(path: Path, notes: list[MotifNote], meter: str, ticks_per_beat: int = 220) -> None:
    numerator, denominator = (int(part) for part in meter.split("/", 1))
    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator, time=0))

    events: list[tuple[int, int, mido.Message]] = []
    for note in notes:
        start_tick = int(round(note.beat * ticks_per_beat))
        end_tick = int(round((note.beat + note.duration_beats) * ticks_per_beat))
        events.append((start_tick, 1, mido.Message("note_on", note=note.pitch, velocity=note.velocity, channel=0)))
        events.append((end_tick, 0, mido.Message("note_off", note=note.pitch, velocity=0, channel=0)))

    last_tick = 0
    for tick, _, message in sorted(events, key=lambda item: (item[0], item[1])):
        message.time = max(0, tick - last_tick)
        track.append(message)
        last_tick = tick
    midi.save(path)


def harmony_for_emotion(emotion: str, bars: int) -> list[dict[str, Any]]:
    progressions = {
        "joy": ["I", "V", "vi", "IV"],
        "calm": ["I", "IV", "I", "V"],
        "neutral": ["I", "V", "I", "IV"],
        "sad": ["vi", "IV", "I", "V"],
        "tense": ["i", "bII", "V", "i"],
    }
    progression = progressions[emotion]
    return [
        {"bars": [bar, bar], "chord": progression[(bar - 1) % len(progression)]}
        for bar in range(1, bars + 1)
    ]


def build_yaml(source_yaml: Path, motif_id: str, notes: list[MotifNote], meter: str, bars: int) -> dict[str, Any]:
    data = yaml.safe_load(source_yaml.read_text(encoding="utf-8")) or {}
    emotion = str(data["emotion"])
    beats_per_bar = int(meter.split("/")[0])
    strong = {
        round(note.beat, 3)
        for note in notes
        if abs(note.beat % beats_per_bar) < 0.01
        or abs(note.beat % beats_per_bar - 2) < 0.01
        or note.duration_beats >= 1.0
    }
    anchors = sorted(strong)[: max(1, min(8, bars * 2))]
    if notes:
        anchors = sorted(set(anchors + [round(notes[-1].beat, 3)]))
    immutable = sorted(set(anchors[: max(1, min(4, len(anchors)))] + ([round(notes[-1].beat, 3)] if notes else [])))
    mutable = [round(note.beat, 3) for note in notes if round(note.beat, 3) not in immutable]
    title = str(data.get("title", motif_id)).replace(" Debug", "")

    return {
        "id": motif_id,
        "title": f"{title} Debug",
        "source_type": data.get("source_type", "lyria_generated"),
        "emotion": emotion,
        "license": data.get("license", {}),
        "meter": meter,
        "bars": bars,
        "home_key": data.get("home_key", "C"),
        "mode": data.get("mode", "gong"),
        "tempo_hint": int(data.get("tempo_hint", DEFAULT_TEMPO[emotion])),
        "pitch_range": [min(note.pitch for note in notes), max(note.pitch for note in notes)],
        "phrases": [{
            "id": "A",
            "bars": [1, bars],
            "role": "motif_debug",
            "anchors": anchors,
            "cadence": "open",
        }],
        "anchors": anchors,
        "immutable_beats": immutable,
        "mutable_beats": mutable,
        "harmony": harmony_for_emotion(emotion, bars),
        "variation_allowed": data.get("variation_allowed", {
            "transpose": [-2, 2],
            "octave_shift": [-12, 12],
            "rhythm_expand": True,
            "rhythm_compress": True,
            "ornament": True,
            "delete_mutable_notes": True,
            "repeat_motif": True,
            "arpeggiate": True,
            "notochord_fill": True,
        }),
        "portrait_behavior": data.get("portrait_behavior", PORTRAITS[emotion]),
        "orchestration": data.get("orchestration", {
            "melody": "xylophone",
            "harmony": "pad",
            "bass": "synth_bass",
            "percussion_profile": "light_pulse" if emotion in {"joy", "neutral"} else "sparse",
            "cymbal_profile": "phrase_boundary_only",
        }),
        "quality": {
            "approved": True,
            "notes": "temporary debug motif auto-clipped from longer melody; replace with human-approved edit before production",
        },
    }


def process_pair(yaml_path: Path, bars: int, overwrite: bool) -> Path:
    midi_path = yaml_path.with_suffix(".mid")
    notes, meter = read_single_melody_midi(midi_path)
    beats_per_bar = int(meter.split("/")[0])
    start = choose_window(notes, bars, beats_per_bar)
    clipped = clipped_notes(notes, start, bars, beats_per_bar)
    if not clipped:
        raise ValueError(f"no notes selected from {midi_path}")

    output_stem = yaml_path.stem.removesuffix("_melody") + "_debug"
    output_midi = yaml_path.with_name(f"{output_stem}.mid")
    output_yaml = yaml_path.with_name(f"{output_stem}.yaml")
    if not overwrite and (output_midi.exists() or output_yaml.exists()):
        return output_yaml

    write_midi(output_midi, clipped, meter)
    payload = build_yaml(yaml_path, output_stem, clipped, meter, bars)
    output_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Create approved short debug motifs from long *_melody MIDI/YAML drafts.")
    parser.add_argument("--root", type=Path, default=PROJECT / "music_library" / "motifs")
    parser.add_argument("--bars", type=int, default=4, choices=range(2, 9))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    outputs: list[Path] = []
    for yaml_path in sorted(args.root.glob("*/*_melody.yaml")):
        outputs.append(process_pair(yaml_path, args.bars, args.overwrite))
    for output in outputs:
        print(output)
    print(f"Created/kept {len(outputs)} approved debug motifs ({args.bars} bars each)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
