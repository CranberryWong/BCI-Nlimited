from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataSample:
    valence: int = 5
    arousal: int = 5
    prob0: float | None = None
    prob1: float | None = None
    source: str = "idle"
    timestamp: float | None = None

    @property
    def confidence(self) -> float:
        values = [value for value in (self.prob0, self.prob1) if value is not None]
        return max(values) if values else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valence": self.valence,
            "arousal": self.arousal,
            "prob0": self.prob0,
            "prob1": self.prob1,
            "confidence": self.confidence,
            "source": self.source,
            "timestamp": self.timestamp,
        }


@dataclass
class RuntimeState:
    running: bool = False
    mode: str = "idle"
    started: bool = False
    finished: bool = False
    model_loaded: bool = False
    xdf_watching: bool = False
    test_stream_running: bool = False
    osc_ready: bool = False
    osc_error: str | None = None
    midi_ready: bool = False
    midi_error: str | None = None
    last_error: str | None = None
    last_log: str | None = None
    latest: DataSample = field(default_factory=DataSample)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "mode": self.mode,
            "started": self.started,
            "finished": self.finished,
            "model_loaded": self.model_loaded,
            "xdf_watching": self.xdf_watching,
            "test_stream_running": self.test_stream_running,
            "osc_ready": self.osc_ready,
            "osc_error": self.osc_error,
            "midi_ready": self.midi_ready,
            "midi_error": self.midi_error,
            "last_error": self.last_error,
            "last_log": self.last_log,
            "latest": self.latest.to_dict(),
        }


class StateStore:
    def __init__(self) -> None:
        self._state = RuntimeState()
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._state.to_dict()

    def latest(self) -> dict[str, Any]:
        with self._lock:
            payload = self._state.latest.to_dict()
            payload.update(
                {
                    "started": self._state.started,
                    "finished": self._state.finished,
                }
            )
            return payload

    def update_sample(
        self,
        valence: int,
        arousal: int,
        prob0: float | None = None,
        prob1: float | None = None,
        source: str = "unknown",
    ) -> DataSample:
        sample = DataSample(
            valence=int(valence),
            arousal=int(arousal),
            prob0=float(prob0) if prob0 is not None else None,
            prob1=float(prob1) if prob1 is not None else None,
            source=source,
            timestamp=time.time(),
        )
        with self._lock:
            self._state.latest = sample
            self._state.started = True
            self._state.finished = False
            self._state.running = True
            self._state.last_log = f"{source}: {sample.valence}, {sample.arousal}"
        return sample

    def patch(self, **values: Any) -> None:
        with self._lock:
            for key, value in values.items():
                if hasattr(self._state, key):
                    setattr(self._state, key, value)

    def log(self, message: str) -> None:
        self.patch(last_log=message)

    def error(self, message: str) -> None:
        self.patch(last_error=message, last_log=message)
