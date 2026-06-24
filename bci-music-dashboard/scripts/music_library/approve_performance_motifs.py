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

from app.music.generation.motif_library import MotifNote, read_motif_midi  # noqa: E402
from scripts.music_library.analyze_motif import PORTRAITS  # noqa: E402
from scripts.music_library.approve_debug_motifs import DEFAULT_TEMPO, harmony_for_emotion  # noqa: E402


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
        pitch_span = max(note.pitch for note in selected) - min(note.pitch for note in selected)
        density_penalty = 0.7 if len(selected) > bars * 24 else 1.0
        score = (len(selected) + pitch_span * 0.2) * density_penalty
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
        duration = min(note.duration_beats, end - note.beat)
        if duration >= 0.125:
            clipped.append(MotifNote(
                beat=round(note.beat - start, 3),
                duration_beats=round(duration, 3),
                pitch=note.pitch,
                velocity=note.velocity,
            ))
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


def companion_metadata(raw_midi: Path) -> dict[str, Any]:
    melody_yaml = raw_midi.with_name(f"{raw_midi.stem}_melody.yaml")
    if melody_yaml.exists():
        return yaml.safe_load(melody_yaml.read_text(encoding="utf-8")) or {}
    return {}


def build_yaml(raw_midi: Path, output_stem: str, notes: list[MotifNote], meter: str, bars: int, emotion: str) -> dict[str, Any]:
    data = companion_metadata(raw_midi)
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
    title = str(data.get("title") or output_stem.replace("_", " ").title()).replace(" Performance", "")
    mode = data.get("mode") or ("yu" if emotion == "sad" else "jue" if emotion == "tense" else "gong")

    return {
        "id": output_stem,
        "title": f"{title} Performance",
        "source_type": "lyria_performance",
        "emotion": emotion,
        "license": data.get("license", {
            "composition": "generated_or_self_curated",
            "model": "Google Lyria",
            "generated_date": "TODO",
            "midi_source": "polyphonic_midi_clip",
            "editor": "TODO",
        }),
        "meter": meter,
        "bars": bars,
        "home_key": data.get("home_key", "C"),
        "mode": mode,
        "tempo_hint": int(data.get("tempo_hint", DEFAULT_TEMPO[emotion])),
        "pitch_range": [min(note.pitch for note in notes), max(note.pitch for note in notes)],
        "phrases": [{
            "id": "A",
            "bars": [1, bars],
            "role": "performance_motif",
            "anchors": anchors,
            "cadence": "open",
        }],
        "anchors": anchors,
        "immutable_beats": immutable,
        "mutable_beats": mutable,
        "harmony": harmony_for_emotion(emotion, bars),
        "variation_allowed": {
            "transpose": [0, 0],
            "octave_shift": [0, 0],
            "rhythm_expand": False,
            "rhythm_compress": False,
            "ornament": False,
            "delete_mutable_notes": False,
            "repeat_motif": True,
            "arpeggiate": False,
            "notochord_fill": False,
        },
        "portrait_behavior": data.get("portrait_behavior", PORTRAITS[emotion]),
        "orchestration": data.get("orchestration", {
            "melody": "xylophone",
            "harmony": "pad",
            "bass": "synth_bass",
            "percussion_profile": "light_pulse" if emotion in {"joy", "neutral"} else "sparse",
            "cymbal_profile": "phrase_boundary_only",
        }),
        "performance": {
            "polyphonic_melody": True,
            "preserve_polyphony": True,
            "source_midi": raw_midi.name,
        },
        "quality": {
            "approved": True,
            "notes": "temporary performance motif clipped from original polyphonic MIDI for debugging",
        },
    }


def process_midi(raw_midi: Path, emotion: str, bars: int, overwrite: bool) -> Path:
    notes, meter = read_motif_midi(raw_midi, allow_overlaps=True)
    beats_per_bar = int(meter.split("/")[0])
    start = choose_window(notes, bars, beats_per_bar)
    clipped = clipped_notes(notes, start, bars, beats_per_bar)
    if not clipped:
        raise ValueError(f"no notes selected from {raw_midi}")

    output_stem = f"{raw_midi.stem}_performance"
    output_midi = raw_midi.with_name(f"{output_stem}.mid")
    output_yaml = raw_midi.with_name(f"{output_stem}.yaml")
    if not overwrite and output_midi.exists() and output_yaml.exists():
        return output_yaml
    write_midi(output_midi, clipped, meter)
    payload = build_yaml(raw_midi, output_stem, clipped, meter, bars, emotion)
    output_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return output_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description="Create approved polyphonic performance motifs from raw MIDI files.")
    parser.add_argument("folder", type=Path, help="Example: music_library/motifs/joy")
    parser.add_argument("--emotion", required=True, choices=tuple(PORTRAITS))
    parser.add_argument("--bars", type=int, default=4, choices=range(2, 9))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    raw_midis = sorted(
        path for path in args.folder.glob("*.mid")
        if not path.stem.endswith(("_melody", "_debug", "_performance"))
    )
    outputs = [process_midi(path, args.emotion, args.bars, args.overwrite) for path in raw_midis]
    for output in outputs:
        print(output)
    print(f"Created/kept {len(outputs)} performance motifs ({args.bars} bars each)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
