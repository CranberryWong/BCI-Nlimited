"""Export a short, standalone Notochord-generated MIDI excerpt.

This intentionally talks to the local checkpoint directly: it neither opens a
MIDI port nor depends on Logic, IAC, or any other playback routing.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import random

import mido
import torch
from notochord import Notochord


ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = Path.home() / "Library/Application Support/Notochord/notochord-latest.ckpt"
OUTPUT = ROOT / "exports/notochord-string-quartet-demo.mid"

# General MIDI programs, one-indexed in Notochord.
INSTRUMENTS = (41, 42, 43, 44)  # violin, viola, cello, contrabass
CHANNEL_FOR_INSTRUMENT = {instrument: channel for channel, instrument in enumerate(INSTRUMENTS)}


def main() -> None:
    if not CHECKPOINT.exists():
        raise SystemExit(f"Notochord checkpoint not found: {CHECKPOINT}")

    random.seed(20260713)
    torch.manual_seed(20260713)
    model = Notochord.from_checkpoint(str(CHECKPOINT))
    model.eval()
    model.reset()

    events: list[tuple[float, int, int, int]] = []
    elapsed = 0.0
    # Sample events until we have a concise, playable excerpt. The constraints
    # keep it in a string-quartet palette and prevent long silent gaps.
    with torch.inference_mode():
        while elapsed < 32.0 and len(events) < 900:
            event = model.query_feed(
                include_inst=set(INSTRUMENTS),
                allow_anon=False,
                allow_end=False,
                min_time=0.025,
                max_time=0.55,
                instrument_temp=0.72,
                pitch_temp=0.78,
                rhythm_temp=0.72,
                timing_temp=0.35,
                velocity_temp=0.65,
            )
            elapsed += float(event["time"])
            if elapsed > 32.0:
                break
            events.append((elapsed, int(event["inst"]), int(event["pitch"]), round(float(event["vel"]))))

    # Ensure every model-held note gets a release, which makes the exported
    # MIDI safe to play in any DAW or media player.
    for instrument, pitch in list(model.held_notes):
        events.append((min(elapsed + 0.8, 33.0), int(instrument), int(pitch), 0))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Notochord String Quartet Demo", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(96), time=0))
    for instrument, channel in CHANNEL_FOR_INSTRUMENT.items():
        track.append(mido.Message("program_change", channel=channel, program=instrument - 1, time=0))

    previous = 0.0
    for timestamp, instrument, pitch, velocity in sorted(events):
        delta = max(0, round((timestamp - previous) * 96 / 60 * midi.ticks_per_beat))
        previous = timestamp
        channel = CHANNEL_FOR_INSTRUMENT[instrument]
        track.append(mido.Message("note_on", channel=channel, note=pitch, velocity=max(0, min(127, velocity)), time=delta))
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(OUTPUT)
    print(f"Wrote {OUTPUT} ({len(events)} Notochord events, {elapsed:.1f} seconds)")


if __name__ == "__main__":
    main()
