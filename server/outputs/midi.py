from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server.config import AppConfig


def scale_1_9_to_0_127(value: float | int) -> int:
    clipped = max(1.0, min(9.0, float(value)))
    return int(round((clipped - 1.0) / 8.0 * 127.0))


def scale_probability_to_0_127(value: float | int | None) -> int:
    if value is None:
        return 0
    clipped = max(0.0, min(1.0, float(value)))
    return int(round(clipped * 127.0))


@dataclass
class MidiMapping:
    valence_cc: int = 20
    arousal_cc: int = 21
    confidence_cc: int = 22
    channel: int = 0


class MidiOutput:
    def __init__(self, config: AppConfig) -> None:
        self._mido: Any | None = None
        self._port: Any | None = None
        self._config = config
        self.error: str | None = None
        self.configure(config)

    @property
    def ready(self) -> bool:
        return self._port is not None

    @staticmethod
    def available_ports() -> list[str]:
        try:
            import mido

            return list(mido.get_output_names())
        except Exception:
            return []

    def configure(self, config: AppConfig) -> None:
        self.close()
        self._config = config
        self.error = None
        if not config.midi_enabled:
            return
        try:
            import mido

            self._mido = mido
            output_names = list(mido.get_output_names())
            if not output_names:
                self.error = "No MIDI output ports found"
                return
            port_name = config.midi_port_name or output_names[0]
            self._port = mido.open_output(port_name)
        except Exception as exc:
            self._port = None
            self.error = str(exc)

    def close(self) -> None:
        if self._port is not None:
            try:
                self._port.close()
            finally:
                self._port = None

    def send(
        self,
        valence: int,
        arousal: int,
        confidence: float | None,
    ) -> list[dict[str, int]]:
        if self._port is None or self._mido is None:
            return []
        mapping = MidiMapping(
            valence_cc=self._config.valence_cc,
            arousal_cc=self._config.arousal_cc,
            confidence_cc=self._config.confidence_cc,
            channel=self._config.midi_channel,
        )
        messages = [
            {"control": mapping.valence_cc, "value": scale_1_9_to_0_127(valence)},
            {"control": mapping.arousal_cc, "value": scale_1_9_to_0_127(arousal)},
            {
                "control": mapping.confidence_cc,
                "value": scale_probability_to_0_127(confidence),
            },
        ]
        for item in messages:
            msg = self._mido.Message(
                "control_change",
                channel=mapping.channel,
                control=item["control"],
                value=item["value"],
            )
            self._port.send(msg)
        return messages

