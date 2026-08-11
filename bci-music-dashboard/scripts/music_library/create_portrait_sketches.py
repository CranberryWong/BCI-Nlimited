"""Create original, bar-aligned audition MIDI for the BCI portrait piece."""

from __future__ import annotations

from pathlib import Path

import mido


PROJECT = Path(__file__).resolve().parents[2]
OUT = PROJECT / "music_library" / "generated"
TPB = 480


def n(beat: float, duration: float, pitch: int, velocity: int) -> tuple[float, float, int, int]:
    return beat, duration, pitch, velocity


def sequence(start: float, pitches: list[int], step: float, velocity: int, duration: float | None = None) -> list[tuple[float, float, int, int]]:
    return [n(start + index * step, duration or step * 0.82, pitch, velocity - (index % 3) * 4) for index, pitch in enumerate(pitches)]


def pulse(beats: list[float], pitch: int, velocity: int) -> list[tuple[float, float, int, int]]:
    return [n(beat, 0.15, pitch, velocity) for beat in beats]


SKETCHES = {
    "calm": {
        "title": "Lake Orbit", "meter": (3, 4), "bpm": 60, "key": "D", "mode": "dorian",
        "energy": 0.20, "density": 0.30, "cadence": "open", "loopable": True,
        "description": "Slow orbital xylophone figures over a deep lake-like electronic floor.",
        "x": sequence(0, [69, 72, 74, 76, 72, 69, 67, 69, 72, 74, 72, 69], 1, 54, 0.78)
             + sequence(0.5, [50, 57, 60, 57, 62, 57, 50, 57, 60, 57, 62, 57], 1, 28, 0.36),
        "drums": pulse([0, 3, 6, 9], 36, 28), "cymbals": [n(11.5, 0.4, 51, 22)],
        "electronic": [n(0, 3, 38, 42), n(0, 3, 45, 34), n(3, 3, 43, 40), n(3, 3, 50, 32), n(6, 3, 38, 40), n(6, 3, 45, 32), n(9, 3, 45, 40), n(9, 3, 52, 32)],
    },
    "joy": {
        "title": "Skipping Light", "meter": (4, 4), "bpm": 116, "key": "G", "mode": "major_pentatonic",
        "energy": 0.72, "density": 0.62, "cadence": "closed", "loopable": True,
        "description": "Two exact xylophone layers leap past each other like flashes of light.",
        "x": sequence(0, [79, 83, 86, 83, 79, 74, 79, 83, 86, 91, 86, 83, 79, 81, 83, 86, 83, 81, 79, 86, 83, 79, 74, 79], 2 / 3, 86, 0.44)
             + sequence(0.25, [62, 67, 71, 67, 62, 67, 71, 67, 64, 69, 72, 69, 62, 67, 71, 67], 1, 48, 0.22),
        "drums": pulse([0, 2, 4, 6, 8, 10, 12, 14], 36, 60) + pulse([1, 3, 5, 7, 9, 11, 13, 15], 42, 42),
        "cymbals": [n(0, 0.35, 51, 34), n(8, 0.35, 51, 36), n(15.5, 0.45, 49, 42)],
        "electronic": [n(0, 4, 43, 34), n(0, 4, 50, 28), n(4, 4, 43, 34), n(4, 4, 50, 28), n(8, 4, 45, 34), n(8, 4, 52, 28), n(12, 4, 43, 34), n(12, 4, 50, 28)],
    },
    "neutral": {
        "title": "Measured Pulse", "meter": (4, 4), "bpm": 78, "key": "C", "mode": "major",
        "energy": 0.42, "density": 0.42, "cadence": "open", "loopable": True,
        "description": "An even, almost cardiac pulse with a melody that never rushes ahead.",
        "x": sequence(0, [64, 67, 69, 67, 65, 69, 72, 69, 64, 67, 71, 67, 62, 65, 67, 69], 1, 62, 0.78)
             + sequence(0.5, [55, 55, 57, 57, 55, 55, 53, 55], 2, 30, 0.25),
        "drums": pulse([0, 2, 4, 6, 8, 10, 12, 14], 36, 46), "cymbals": [n(7.75, 0.25, 51, 22), n(15.75, 0.25, 51, 24)],
        "electronic": [n(0, 4, 36, 38), n(0, 4, 43, 30), n(4, 4, 41, 38), n(4, 4, 48, 30), n(8, 4, 36, 38), n(8, 4, 43, 30), n(12, 4, 43, 38), n(12, 4, 50, 30)],
    },
    "sad": {
        "title": "Falling Beads", "meter": (3, 4), "bpm": 66, "key": "A", "mode": "minor",
        "energy": 0.34, "density": 0.56, "cadence": "open", "loopable": False,
        "description": "Separated falling notes gather into a melody that nearly resolves, then lets go.",
        "x": sequence(0, [76, 72, 69, 74, 71, 67, 72, 69, 64, 71, 69, 68], 1, 58, 0.72)
             + sequence(0.25, [84, 81, 78, 84, 81, 77, 81, 78, 76, 79, 77, 76], 0.95, 38, 0.22),
        "drums": pulse([0, 3, 6, 9], 36, 24), "cymbals": [n(11.75, 0.25, 51, 20)],
        "electronic": [n(0, 3, 33, 38), n(0, 3, 40, 30), n(3, 3, 38, 36), n(3, 3, 45, 28), n(6, 3, 33, 36), n(6, 3, 40, 28), n(9, 3, 40, 34), n(9, 3, 47, 26)],
    },
    "tense": {
        "title": "Storm Mechanism", "meter": (6, 8), "bpm": 168, "key": "D", "mode": "minor",
        "energy": 0.90, "density": 0.88, "cadence": "open", "loopable": True,
        "description": "A precise six-eight machine chase: xylophone supplies melody and storm texture.",
        "x": sequence(0, [74, 77, 81, 77, 74, 69, 76, 79, 82, 79, 76, 70, 74, 77, 81, 84, 81, 77, 76, 79, 82, 86, 82, 79], 0.5, 90, 0.34)
             + sequence(0, [50, 57, 62, 50, 57, 62, 52, 58, 64, 52, 58, 64, 50, 57, 62, 50, 57, 62, 52, 58, 64, 52, 58, 64], 0.5, 52, 0.18),
        "drums": pulse([0, 3, 6, 9], 36, 76) + pulse([1.5, 4.5, 7.5, 10.5], 38, 72) + pulse([0.5, 1, 2, 2.5, 3.5, 4, 5, 5.5, 6.5, 7, 8, 8.5, 9.5, 10, 11, 11.5], 42, 54),
        "cymbals": [n(0, 0.3, 49, 46), n(6, 0.3, 51, 38), n(11.5, 0.5, 49, 54)],
        "electronic": [n(0, 3, 38, 44), n(0, 3, 45, 36), n(3, 3, 40, 44), n(3, 3, 46, 36), n(6, 3, 38, 46), n(6, 3, 45, 38), n(9, 3, 40, 46), n(9, 3, 46, 38)],
    },
}


def write_track(midi: mido.MidiFile, name: str, channel: int, notes: list[tuple[float, float, int, int]], program: int | None = None) -> None:
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=name, time=0))
    if program is not None:
        track.append(mido.Message("program_change", channel=channel, program=program, time=0))
    events = []
    for beat, duration, pitch, velocity in notes:
        events.extend([(round(beat * TPB), 1, pitch, velocity), (round((beat + duration) * TPB), 0, pitch, 0)])
    cursor = 0
    for tick, is_on, pitch, velocity in sorted(events, key=lambda event: (event[0], event[1])):
        track.append(mido.Message("note_on" if is_on else "note_off", channel=channel, note=pitch, velocity=velocity, time=tick - cursor))
        cursor = tick


def write_metadata(path: Path, emotion: str, spec: dict) -> None:
    numerator, denominator = spec["meter"]
    beats_per_bar = numerator * 4 / denominator
    text = f'''id: {emotion}_001_portrait_sketch
title: {spec["title"]}
source_type: original_bci_portrait_sketch
status: audition_only
emotion: {emotion}
meter: {numerator}/{denominator}
bars: 4
beats_per_bar: {beats_per_bar:g}
tempo_bpm: {spec["bpm"]}
home_key: {spec["key"]}
mode: {spec["mode"]}
duration_beats: {beats_per_bar * 4:g}
loopable: {str(spec["loopable"]).lower()}
cadence: {spec["cadence"]}
energy: {spec["energy"]:.2f}
density: {spec["density"]:.2f}
description: "{spec["description"]}"
instruments:
  xylophone: {{role: main_motif_and_machine_polyphony, midi_track: Xylophone, midi_channel: 1}}
  drums: {{role: pulse_and_energy, midi_track: Drums, midi_channel: 10}}
  cymbals: {{role: phrase_boundary_and_transition, midi_track: Cymbals, midi_channel: 10}}
  electronic: {{role: sustained_harmony_and_space, midi_track: Electronic, midi_channel: 2}}
performance:
  polyphonic_xylophone: true
  starts_on_bar: 1
  clean_note_offs: true
  max_velocity: 90
  no_pitch_bend: true
  no_control_changes: true
quality:
  approved: false
  notes: "Original composition sketch. Audition before runtime approval."
'''
    path.write_text(text, encoding="ascii")


def main() -> None:
    for emotion, spec in SKETCHES.items():
        output = OUT / emotion
        output.mkdir(parents=True, exist_ok=True)
        midi = mido.MidiFile(ticks_per_beat=TPB)
        conductor = mido.MidiTrack()
        midi.tracks.append(conductor)
        numerator, denominator = spec["meter"]
        conductor.append(mido.MetaMessage("track_name", name=f"{spec['title']} conductor", time=0))
        conductor.append(mido.MetaMessage("time_signature", numerator=numerator, denominator=denominator, time=0))
        conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(spec["bpm"]), time=0))
        write_track(midi, "Xylophone", 0, spec["x"], program=13)
        write_track(midi, "Electronic", 1, spec["electronic"], program=88)
        write_track(midi, "Drums", 9, spec["drums"])
        write_track(midi, "Cymbals", 9, spec["cymbals"])
        stem = f"{emotion}_001_portrait_sketch"
        midi.save(output / f"{stem}.mid")
        write_metadata(output / f"{stem}.yaml", emotion, spec)
    print(f"Created {len(SKETCHES)} sketches under {OUT}")


if __name__ == "__main__":
    main()
