from __future__ import annotations

from dataclasses import dataclass

from server.config import AppConfig


@dataclass
class OscPayload:
    valence: int
    arousal: int
    prob0: float | None = None
    prob1: float | None = None

    def to_list(self) -> list[float | int]:
        return [
            int(self.valence),
            int(self.arousal),
            float(self.prob0) if self.prob0 is not None else 0.0,
            float(self.prob1) if self.prob1 is not None else 0.0,
        ]


class OscOutput:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = None
        self._target: tuple[str, int] | None = None
        self.error: str | None = None
        self.configure(config)

    @property
    def ready(self) -> bool:
        return self._client is not None

    def configure(self, config: AppConfig) -> None:
        self._config = config
        target = (config.osc_target_ip, int(config.osc_target_port))
        if target == self._target and self._client is not None:
            return
        try:
            from pythonosc import udp_client

            self._client = udp_client.SimpleUDPClient(target[0], target[1])
            self._target = target
            self.error = None
        except Exception as exc:
            self._client = None
            self._target = None
            self.error = str(exc)

    def send(
        self,
        valence: int,
        arousal: int,
        prob0: float | None = None,
        prob1: float | None = None,
    ) -> list[float | int]:
        if self._client is None:
            raise RuntimeError("OSC client is not configured")
        payload = OscPayload(valence, arousal, prob0, prob1).to_list()
        self._client.send_message(self._config.osc_address, payload)
        return payload
