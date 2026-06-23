from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import mido

from app.music.schemas import SegmentNote


@dataclass
class ParsedMidi:
    path: Path
    ticks_per_beat: int
    notes: list[SegmentNote]
    time_signature: tuple[int, int]
    bpm: int


def parse_melody(path: Path) -> ParsedMidi:
    midi = mido.MidiFile(path)
    signatures: set[tuple[int, int]] = set()
    tempo = mido.bpm2tempo(84)
    candidate_tracks: list[list[SegmentNote]] = []
    for track_index, track in enumerate(midi.tracks):
        absolute = 0
        active: dict[tuple[int, int], tuple[int, int]] = {}
        notes: list[SegmentNote] = []
        is_drum = False
        for message in track:
            absolute += message.time
            if message.type == "time_signature":
                signatures.add((message.numerator, message.denominator))
            elif message.type == "set_tempo":
                tempo = message.tempo
            elif message.type in {"note_on", "note_off"}:
                is_drum = is_drum or message.channel == 9
                key = (message.channel, message.note)
                if message.type == "note_on" and message.velocity > 0:
                    active[key] = (absolute, message.velocity)
                elif key in active:
                    started, velocity = active.pop(key)
                    duration = max(1, absolute - started)
                    notes.append(SegmentNote(
                        beat=started / midi.ticks_per_beat,
                        duration_beats=duration / midi.ticks_per_beat,
                        pitch=message.note,
                        velocity=velocity,
                        track_id=f"track-{track_index}",
                        channel=message.channel + 1,
                    ))
        if notes and not is_drum:
            candidate_tracks.append(notes)
    if len(candidate_tracks) != 1:
        raise ValueError(f"expected exactly one non-drum melody track, found {len(candidate_tracks)}")
    if signatures and signatures != {(4, 4)}:
        raise ValueError(f"only 4/4 is supported, found {sorted(signatures)}")
    notes = sorted(candidate_tracks[0], key=lambda item: item.beat)
    if not notes:
        raise ValueError("melody track contains no completed notes")
    if any(left.beat + left.duration_beats > right.beat + 0.01 for left, right in zip(notes, notes[1:])):
        raise ValueError("melody notes overlap")
    return ParsedMidi(path, midi.ticks_per_beat, notes, (4, 4), round(mido.tempo2bpm(tempo)))


def write_midi(path: Path, notes: list[SegmentNote], bpm: int) -> None:
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    events: list[tuple[int, mido.Message]] = []
    for note in notes:
        start = round(note.beat * midi.ticks_per_beat)
        end = round((note.beat + note.duration_beats) * midi.ticks_per_beat)
        events.append((start, mido.Message("note_on", note=note.pitch, velocity=note.velocity, channel=0)))
        events.append((end, mido.Message("note_off", note=note.pitch, velocity=0, channel=0)))
    last = 0
    for tick, message in sorted(events, key=lambda item: (item[0], item[1].type == "note_on")):
        message.time = max(0, tick - last)
        track.append(message)
        last = tick
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)
