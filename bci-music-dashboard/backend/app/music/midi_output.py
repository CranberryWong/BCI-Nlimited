from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

import mido

from app.music.schemas import MusicEvent, TrackConfig


@dataclass
class MidiStatus:
    mode: str
    ports: list[str]
    detail: str = ""


class MidiOutput:
    def __init__(self) -> None:
        self._port = None
        self.status = self._probe()

    def list_ports(self) -> MidiStatus:
        self.status = self._probe()
        return self.status

    def send_event(self, track: TrackConfig, event: MusicEvent) -> None:
        if event.type not in {"note_on", "note_off"} or event.pitch is None:
            return
        port = self._ensure_port()
        if port is None:
            return
        port.send(
            mido.Message(
                event.type,
                note=event.pitch,
                velocity=event.velocity or 0,
                channel=max(0, track.midi_channel - 1),
            )
        )

    def _ensure_port(self):
        if self.status.mode != "rtmidi":
            return None
        if self._port is None and self.status.ports:
            try:
                self._port = mido.open_output(self.status.ports[0])
            except Exception as exc:
                self.status = MidiStatus("mock", [], str(exc))
        return self._port

    @staticmethod
    def _probe() -> MidiStatus:
        try:
            probe = subprocess.run(
                [sys.executable, "-c", "import json, mido; print(json.dumps(list(mido.get_output_names())))"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            if probe.returncode != 0:
                return MidiStatus("mock", [], (probe.stderr or "MIDI backend probe failed").strip())
            ports = json.loads(probe.stdout.strip() or "[]")
            return MidiStatus("rtmidi" if ports else "mock", ports, "" if ports else "no MIDI outputs detected")
        except Exception as exc:
            return MidiStatus("mock", [], str(exc))
