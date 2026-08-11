from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import mido
import soundfile as sf

from .transcription import NoteEvent


class MidiPort(Protocol):
    def send(self, message: mido.Message) -> None: ...

    def close(self) -> None: ...


def list_midi_ports() -> list[str]:
    """Probe CoreMIDI in a subprocess so a backend crash is reportable."""

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, mido; print(json.dumps(list(mido.get_output_names())))",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=8,
    )
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout or "CoreMIDI probe failed").strip()
        raise RuntimeError(f"Unable to query MIDI outputs: {detail}")
    return list(json.loads(probe.stdout.strip() or "[]"))


def select_midi_port(ports: list[str], requested: str | None) -> str:
    if not ports:
        raise RuntimeError(
            "No MIDI output is available. Enable an IAC Bus in Audio MIDI Setup."
        )
    if requested:
        exact = [name for name in ports if name == requested]
        if exact:
            return exact[0]
        partial = [name for name in ports if requested.casefold() in name.casefold()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise RuntimeError(
                f"MIDI port selector {requested!r} is ambiguous: {partial}"
            )
        raise RuntimeError(f"MIDI port {requested!r} not found. Available: {ports}")

    iac_ports = [name for name in ports if "iac" in name.casefold()]
    if not iac_ports:
        raise RuntimeError(
            f"No IAC MIDI output found. Available outputs: {ports}. "
            "Pass --midi-port explicitly if Logic uses another port."
        )
    return sorted(iac_ports)[0]


class MidiOutput:
    """Send note events while keeping one authoritative active-note state."""

    def __init__(self, port: MidiPort, channel: int = 1):
        if not 1 <= channel <= 16:
            raise ValueError("MIDI channel must be in 1..16")
        self.port = port
        self.channel = channel - 1
        self.active_note: int | None = None

    @classmethod
    def open(cls, port_name: str, channel: int = 1) -> "MidiOutput":
        return cls(mido.open_output(port_name), channel)

    def send(self, event: NoteEvent) -> None:
        if event.kind == "note_on":
            if self.active_note is not None and self.active_note != event.note:
                self._send_note_off(self.active_note)
            self.port.send(
                mido.Message(
                    "note_on",
                    note=event.note,
                    velocity=event.velocity,
                    channel=self.channel,
                )
            )
            self.active_note = event.note
        elif event.kind == "note_off":
            self._send_note_off(event.note)
            if self.active_note == event.note:
                self.active_note = None
        else:
            raise ValueError(f"Unsupported event kind: {event.kind}")

    def all_notes_off(self) -> None:
        if self.active_note is not None:
            self._send_note_off(self.active_note)
            self.active_note = None
        self.port.send(
            mido.Message(
                "control_change", channel=self.channel, control=123, value=0
            )
        )
        self.port.send(
            mido.Message(
                "control_change", channel=self.channel, control=120, value=0
            )
        )

    def close(self) -> None:
        try:
            self.all_notes_off()
        finally:
            self.port.close()

    def _send_note_off(self, note: int) -> None:
        self.port.send(
            mido.Message(
                "note_off", note=note, velocity=0, channel=self.channel
            )
        )


@dataclass(frozen=True)
class ArtifactPaths:
    wav: Path
    midi: Path
    csv: Path


class ArtifactWriter:
    """Stream WAV/CSV to disk and build a timestamp-faithful MIDI file."""

    def __init__(self, output_dir: Path, sample_rate: int, channels: int = 2):
        output_dir.mkdir(parents=True, exist_ok=True)
        stem = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.paths = ArtifactPaths(
            output_dir / f"{stem}.wav",
            output_dir / f"{stem}.mid",
            output_dir / f"{stem}-events.csv",
        )
        self._wav = sf.SoundFile(
            self.paths.wav,
            mode="w",
            samplerate=sample_rate,
            channels=channels,
            subtype="PCM_16",
        )
        self._csv_file = self.paths.csv.open("w", newline="", encoding="utf-8")
        self._csv = csv.writer(self._csv_file)
        self._csv.writerow(
            ["timestamp", "kind", "note", "velocity", "frequency", "confidence"]
        )
        self._events: list[NoteEvent] = []

    def write_audio(self, samples) -> None:
        self._wav.write(samples)

    def write_event(self, event: NoteEvent) -> None:
        self._events.append(event)
        self._csv.writerow(
            [
                f"{event.timestamp:.6f}",
                event.kind,
                event.note,
                event.velocity,
                "" if event.frequency is None else f"{event.frequency:.3f}",
                f"{event.confidence:.4f}",
            ]
        )
        self._csv_file.flush()

    def close(self, midi_channel: int = 1) -> ArtifactPaths:
        self._wav.close()
        self._csv_file.close()
        self._write_midi(midi_channel)
        return self.paths

    def _write_midi(self, midi_channel: int) -> None:
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        midi.tracks.append(track)
        tempo = mido.bpm2tempo(120)
        track.append(mido.MetaMessage("track_name", name="Magenta Flow"))
        track.append(mido.MetaMessage("set_tempo", tempo=tempo))
        previous = 0.0
        for event in sorted(self._events, key=lambda value: value.timestamp):
            delta_seconds = max(0.0, event.timestamp - previous)
            ticks = int(round(mido.second2tick(delta_seconds, 480, tempo)))
            track.append(
                mido.Message(
                    event.kind,
                    note=event.note,
                    velocity=event.velocity,
                    channel=midi_channel - 1,
                    time=ticks,
                )
            )
            previous = event.timestamp
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.save(self.paths.midi)

