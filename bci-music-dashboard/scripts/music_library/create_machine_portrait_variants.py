"""Create machine-safe tension and release variations for the portrait sketches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mido


PROJECT = Path(__file__).resolve().parents[2]
OUT = PROJECT / "music_library" / "generated"
TPB = 480


@dataclass(frozen=True)
class Variant:
    emotion: str
    role: str
    title: str
    meter: tuple[int, int]
    bpm: int
    key: str
    mode: str
    frame_beats: float
    frames: list[list[int]]
    energy: float
    density: float
    cadence: str
    loopable: bool
    description: str


def v(*pitches: int) -> list[int]:
    return list(pitches)


# Every xylophone frame is at least one second apart for a repeated pitch.
# The apparent density comes from the number and placement of different keys in
# a frame, not from impossible repeated strikes on an individual key.
VARIANTS = [
    Variant("calm", "loop", "Lake Orbit - Machine Loop", (3, 4), 72, "D", "dorian", 1.5,
        [v(50, 57, 69, 72), v(45, 52, 64, 74), v(50, 57, 67, 72), v(45, 52, 62, 69), v(50, 57, 69, 76), v(45, 52, 64, 72), v(50, 57, 67, 74), v(45, 52, 62, 69)],
        .24, .34, "open", True, "A stable orbital pattern made from slow, machine-precise rings."),
    Variant("joy", "loop", "Skipping Light - Machine Loop", (4, 4), 120, "G", "major_pentatonic", 1,
        [v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86), v(55, 62, 67, 79, 83), v(57, 64, 69, 81, 86)],
        .64, .58, "closed", True, "Alternating pentatonic arrays create a bright, skipping pulse."),
    Variant("neutral", "loop", "Measured Pulse - Machine Loop", (4, 4), 78, "C", "major", 2,
        [v(36, 43, 55, 60, 64), v(41, 48, 57, 62, 67), v(36, 43, 55, 60, 64), v(43, 50, 59, 65, 67), v(36, 43, 55, 60, 64), v(41, 48, 57, 62, 67), v(36, 43, 55, 60, 64), v(43, 50, 59, 65, 67)],
        .38, .42, "open", True, "Regular arrays establish a calm, measured machine pulse."),
    Variant("sad", "loop", "Falling Beads - Machine Loop", (3, 4), 66, "A", "minor", 1.5,
        [v(45, 52, 69, 76), v(40, 47, 67, 74), v(45, 52, 64, 72), v(40, 47, 68, 71), v(45, 52, 69, 76), v(40, 47, 67, 74), v(45, 52, 64, 72), v(40, 47, 68, 71)],
        .30, .38, "open", True, "A repeating fall of separated note clusters, held just before resolution."),
    Variant("tense", "loop", "Storm Mechanism - Machine Loop", (6, 8), 120, "D", "minor", 1,
        [v(38, 45, 50, 57, 62, 74, 77), v(40, 46, 52, 58, 64, 76, 79), v(38, 45, 50, 57, 62, 74, 77), v(40, 46, 52, 58, 64, 76, 79), v(38, 45, 50, 57, 62, 74, 77), v(40, 46, 52, 58, 64, 76, 79), v(38, 45, 50, 57, 62, 74, 77), v(40, 46, 52, 58, 64, 76, 79), v(38, 45, 50, 57, 62, 74, 77), v(40, 46, 52, 58, 64, 76, 79), v(38, 45, 50, 57, 62, 74, 77), v(40, 46, 52, 58, 64, 76, 79)],
        .74, .68, "open", True, "Alternating minor arrays keep a constant mechanical threat."),
    Variant("calm", "tension", "Lake Orbit - Ripples Gather", (3, 4), 72, "D", "dorian", 1.5,
        [v(50, 57, 62, 69, 72), v(52, 57, 62, 65, 72, 76), v(50, 57, 60, 67, 74), v(45, 52, 57, 64, 69, 74), v(50, 57, 62, 69, 72, 76), v(52, 57, 65, 72, 74), v(50, 57, 60, 67, 72), v(45, 52, 57, 64, 69, 76)],
        .46, .56, "open", True, "The lake motif thickens into slow, overlapping rings."),
    Variant("calm", "release", "Lake Orbit - Water Clears", (3, 4), 54, "D", "dorian", 3,
        [v(50, 57, 69), v(45, 52, 64, 72), v(50, 57, 69), v(45, 52, 62)],
        .12, .16, "closed", False, "Only the outer edge of each ripple remains before silence."),
    Variant("joy", "tension", "Skipping Light - Overdrive", (4, 4), 120, "G", "major_pentatonic", 1,
        [v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86), v(55, 62, 67, 71, 79, 83), v(57, 64, 69, 74, 81, 86)],
        .90, .82, "open", True, "The playful cell becomes a bright, machine-precise cascade."),
    Variant("joy", "release", "Skipping Light - Afterimage", (4, 4), 84, "G", "major_pentatonic", 4,
        [v(55, 62, 79, 83), v(57, 64, 81, 86), v(55, 62, 79), v(55, 62, 67)],
        .28, .22, "closed", False, "The bright skips leave four widely spaced afterimages."),
    Variant("neutral", "tension", "Measured Pulse - Pressure", (4, 4), 72, "C", "major", 1.5,
        [v(36, 43, 55, 60, 64), v(38, 45, 57, 62, 67), v(36, 43, 55, 60, 64, 69), v(41, 48, 57, 65, 69), v(36, 43, 55, 60, 64, 71), v(43, 50, 59, 65, 67), v(36, 43, 55, 60, 64), v(38, 45, 57, 62, 67)],
        .60, .52, "open", True, "The steady pulse gains pressure without losing its regular frame."),
    Variant("neutral", "release", "Measured Pulse - Resting Rate", (4, 4), 60, "C", "major", 4,
        [v(36, 43, 60, 64), v(41, 48, 62, 65), v(36, 43, 60), v(36, 43)],
        .18, .18, "closed", False, "The pulse becomes sparse enough to hand the scene elsewhere."),
    Variant("sad", "tension", "Falling Beads - Held Back", (3, 4), 72, "A", "minor", 1.5,
        [v(45, 52, 57, 69, 72, 76), v(40, 47, 52, 67, 71, 74), v(45, 52, 57, 64, 69, 72), v(40, 47, 55, 68, 71, 76), v(45, 52, 57, 69, 72, 81), v(40, 47, 52, 67, 71), v(45, 52, 57, 64, 69, 76), v(40, 47, 55, 67, 74)],
        .58, .54, "open", True, "Falling beads collect into clusters that refuse to resolve."),
    Variant("sad", "release", "Falling Beads - Last Drop", (3, 4), 54, "A", "minor", 3,
        [v(45, 52, 69, 76), v(40, 47, 67, 74), v(45, 52, 64, 72), v(45, 52, 57)],
        .14, .16, "open", False, "The melody is reduced to four fading drops."),
    Variant("tense", "tension", "Storm Mechanism - Full Array", (6, 8), 120, "D", "minor", 1,
        [v(38, 45, 50, 57, 62, 69, 74, 77, 81), v(40, 46, 52, 58, 64, 70, 76, 79, 82), v(38, 45, 50, 57, 62, 69, 74, 77, 81), v(40, 46, 52, 58, 64, 70, 76, 79, 82), v(38, 45, 50, 57, 62, 69, 74, 77, 81), v(40, 46, 52, 58, 64, 70, 76, 79, 82), v(38, 45, 50, 57, 62, 69, 74, 77, 81), v(40, 46, 52, 58, 64, 70, 76, 79, 82), v(38, 45, 50, 57, 62, 69, 74, 77, 81), v(40, 46, 52, 58, 64, 70, 76, 79, 82), v(38, 45, 50, 57, 62, 69, 74, 77, 81), v(40, 46, 52, 58, 64, 70, 76, 79, 82)],
        .98, .92, "open", True, "Six dense arrays alternate like a storm driven by a single clock."),
    Variant("tense", "release", "Storm Mechanism - Residual Charge", (6, 8), 84, "D", "minor", 3,
        [v(38, 45, 62, 74, 81), v(40, 46, 64, 76, 82), v(38, 45, 57, 69, 74), v(38, 45, 50)],
        .32, .26, "open", False, "The storm leaves one charged array per bar, then a low residue."),
]


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
    for tick, on, pitch, velocity in sorted(events, key=lambda event: (event[0], event[1])):
        track.append(mido.Message("note_on" if on else "note_off", channel=channel, note=pitch, velocity=velocity, time=tick - cursor))
        cursor = tick


def xylophone_notes(variant: Variant) -> list[tuple[float, float, int, int]]:
    notes = []
    for index, pitches in enumerate(variant.frames):
        beat = index * variant.frame_beats
        velocity = min(92, round(46 + variant.energy * 46))
        for pitch_index, pitch in enumerate(pitches):
            notes.append((beat, min(.55, variant.frame_beats * .55), pitch, max(26, velocity - (pitch_index % 4) * 5)))
    return notes


def electronic_notes(variant: Variant) -> list[tuple[float, float, int, int]]:
    beats_per_bar = variant.meter[0] * 4 / variant.meter[1]
    total_beats = beats_per_bar * 4
    root = {"calm": 38, "joy": 43, "neutral": 36, "sad": 33, "tense": 38}[variant.emotion]
    return [(bar * beats_per_bar, beats_per_bar, root + shift, 34) for bar, shift in enumerate((0, 5, 0, 7))] + [(0, total_beats, root + 12, 20)]


def percussion_notes(variant: Variant) -> tuple[list[tuple[float, float, int, int]], list[tuple[float, float, int, int]]]:
    beats_per_bar = variant.meter[0] * 4 / variant.meter[1]
    total_beats = beats_per_bar * 4
    drums = [(beat, .15, 36, round(32 + variant.energy * 42)) for beat in range(0, int(total_beats), max(1, round(beats_per_bar)))]
    cymbal = [(total_beats - min(.25, beats_per_bar / 2), .2, 51, round(20 + variant.energy * 30))]
    return drums, cymbal


def write_metadata(path: Path, variant: Variant) -> None:
    numerator, denominator = variant.meter
    beats_per_bar = numerator * 4 / denominator
    text = f'''id: {variant.emotion}_001_{variant.role}_machine
title: {variant.title}
source_type: original_bci_machine_portrait_variant
status: audition_only
emotion: {variant.emotion}
role: {variant.role}
derived_from: {variant.emotion}_001_portrait_sketch
meter: {numerator}/{denominator}
bars: 4
tempo_bpm: {variant.bpm}
home_key: {variant.key}
mode: {variant.mode}
frame_beats: {variant.frame_beats:g}
same_key_minimum_interval_seconds: 1.0
loopable: {str(variant.loopable).lower()}
cadence: {variant.cadence}
energy: {variant.energy:.2f}
density: {variant.density:.2f}
description: "{variant.description}"
instruments:
  xylophone: {{role: machine_polyphonic_main_voice, midi_track: Xylophone, midi_channel: 1}}
  drums: {{role: macro_pulse, midi_track: Drums, midi_channel: 10}}
  cymbals: {{role: phrase_boundary, midi_track: Cymbals, midi_channel: 10}}
  electronic: {{role: sustained_space, midi_track: Electronic, midi_channel: 2}}
performance:
  polyphonic_xylophone: true
  simultaneous_notes_allowed: true
  same_key_minimum_interval_seconds: 1.0
  clean_note_offs: true
  no_pitch_bend: true
quality:
  approved: false
  notes: "Original machine-safe variation. Test on physical xylophone before approval."
'''
    path.write_text(text, encoding="ascii")


def write_variant(variant: Variant) -> None:
    output = OUT / variant.emotion
    output.mkdir(parents=True, exist_ok=True)
    midi = mido.MidiFile(ticks_per_beat=TPB)
    conductor = mido.MidiTrack()
    midi.tracks.append(conductor)
    conductor.append(mido.MetaMessage("track_name", name=f"{variant.title} conductor", time=0))
    conductor.append(mido.MetaMessage("time_signature", numerator=variant.meter[0], denominator=variant.meter[1], time=0))
    conductor.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(variant.bpm), time=0))
    drums, cymbals = percussion_notes(variant)
    write_track(midi, "Xylophone", 0, xylophone_notes(variant), program=13)
    write_track(midi, "Electronic", 1, electronic_notes(variant), program=88)
    write_track(midi, "Drums", 9, drums)
    write_track(midi, "Cymbals", 9, cymbals)
    stem = f"{variant.emotion}_001_{variant.role}_machine"
    midi.save(output / f"{stem}.mid")
    write_metadata(output / f"{stem}.yaml", variant)


def main() -> None:
    for variant in VARIANTS:
        write_variant(variant)
    print(f"Created {len(VARIANTS)} machine-safe variants under {OUT}")


if __name__ == "__main__":
    main()
