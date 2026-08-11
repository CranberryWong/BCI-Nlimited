from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable

from .schemas import InputSample


class AuxiliaryInputSimulator:
    """Deterministic auxiliary sensor simulator for rehearsal and diagnostics."""

    def __init__(self, ingest: Callable[[InputSample], bool], interval_seconds: float = 0.5) -> None:
        self.ingest = ingest
        self.interval_seconds = max(0.1, interval_seconds)
        self.task: asyncio.Task | None = None
        self.sequence = 0

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def start(self) -> None:
        if not self.running:
            self.task = asyncio.create_task(self._run(), name="adaptive-auxiliary-simulator")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None

    async def _run(self) -> None:
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            wave = 0.5 + 0.35 * math.sin(elapsed / 7.0)
            inverse = 1.0 - wave
            self.sequence += 1
            now = time.time()
            samples = (
                InputSample(source_id="sensor.heart_rate", kind="heart_rate", timestamp=now, sequence=self.sequence, quality=0.9, values={"bpm": 62 + wave * 54}),
                InputSample(source_id="sensor.motion", kind="motion", timestamp=now, sequence=self.sequence, quality=0.9, values={"intensity": wave, "cadence": 55 + wave * 80}),
                InputSample(source_id="sensor.light", kind="light", timestamp=now, sequence=self.sequence, quality=0.9, values={"lux": 20 + inverse * 1800}),
                InputSample(source_id="sensor.posture", kind="posture", timestamp=now, sequence=self.sequence, quality=0.9, values={
                    "expansion": wave, "symmetry": 0.75 + inverse * 0.2,
                    "verticality": 0.45 + wave * 0.45, "gesture": "reach" if wave > 0.78 else "idle",
                }),
            )
            for sample in samples:
                self.ingest(sample)
            await asyncio.sleep(self.interval_seconds)
