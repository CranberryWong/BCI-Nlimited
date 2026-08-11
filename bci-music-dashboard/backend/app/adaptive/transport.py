from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TransportPosition:
    timestamp: float
    elapsed_seconds: float
    absolute_beat: float
    bar: int
    beat: float
    phase: float


class TransportClock:
    """Single monotonic musical clock shared by all output roles."""

    def __init__(self, bpm: float = 84.0, beats_per_bar: int = 4) -> None:
        self.bpm = bpm
        self.beats_per_bar = beats_per_bar
        self.started_at: float | None = None
        self.offset_beats = 0.0

    @property
    def running(self) -> bool:
        return self.started_at is not None

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    def start(self, bpm: float | None = None) -> None:
        if bpm is not None:
            self.bpm = float(bpm)
        self.offset_beats = 0.0
        self.started_at = time.monotonic()

    def stop(self) -> None:
        self.started_at = None
        self.offset_beats = 0.0

    def set_bpm(self, bpm: float) -> None:
        if self.running:
            current = self.position().absolute_beat
            self.offset_beats = current
            self.started_at = time.monotonic()
        self.bpm = max(30.0, min(220.0, float(bpm)))

    def position(self) -> TransportPosition:
        elapsed = max(0.0, time.monotonic() - self.started_at) if self.started_at is not None else 0.0
        absolute = self.offset_beats + elapsed / self.seconds_per_beat
        bar = int(absolute // self.beats_per_bar)
        beat = absolute % self.beats_per_bar
        return TransportPosition(
            timestamp=time.time(),
            elapsed_seconds=elapsed,
            absolute_beat=absolute,
            bar=bar,
            beat=beat,
            phase=beat / self.beats_per_bar,
        )
