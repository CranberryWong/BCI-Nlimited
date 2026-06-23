from pathlib import Path

import mido


PROJECT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT / "music_library" / "themes" / "ode_to_joy" / "melody.mid"
TPB = 480

# (beat, duration, pitch), self-transcribed public-domain theme in C major.
NOTES = [
    (0, 1, 64), (1, 1, 64), (2, 1, 65), (3, 1, 67),
    (4, 1, 67), (5, 1, 65), (6, 1, 64), (7, 1, 62),
    (8, 1, 60), (9, 1, 60), (10, 1, 62), (11, 1, 64),
    (12, 1.5, 64), (13.5, 0.5, 62), (14, 2, 62),
    (16, 1, 64), (17, 1, 64), (18, 1, 65), (19, 1, 67),
    (20, 1, 67), (21, 1, 65), (22, 1, 64), (23, 1, 62),
    (24, 1, 60), (25, 1, 60), (26, 1, 62), (27, 1, 64),
    (28, 1.5, 62), (29.5, 0.5, 60), (30, 2, 60),
]


def main() -> None:
    events = []
    for beat, duration, pitch in NOTES:
        events.append((round(beat * TPB), 1, pitch, 82))
        events.append((round((beat + duration) * TPB), 0, pitch, 0))
    events.sort(key=lambda item: (item[0], item[1]))

    midi = mido.MidiFile(ticks_per_beat=TPB)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Ode to Joy - self transcribed"))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(84)))
    cursor = 0
    for tick, is_on, pitch, velocity in events:
        delta = tick - cursor
        cursor = tick
        track.append(mido.Message(
            "note_on" if is_on else "note_off",
            note=pitch,
            velocity=velocity,
            channel=0,
            time=delta,
        ))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    midi.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
