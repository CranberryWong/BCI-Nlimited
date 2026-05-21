from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable


SimulatorCallback = Callable[[int, int, float, float], Awaitable[None]]


class SimulatorRunner:
    def __init__(self, on_payload: SimulatorCallback) -> None:
        self.on_payload = on_payload
        self.task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def start(self) -> None:
        if not self.running:
            self.task = asyncio.create_task(self._run(), name="bci-simulator")

    async def stop(self) -> None:
        if not self.task:
            return
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.task = None

    async def _run(self) -> None:
        while True:
            valence = random.randint(1, 9)
            arousal = random.randint(1, 9)
            prob0 = round(random.uniform(0.1, 0.9), 3)
            await self.on_payload(valence, arousal, prob0, round(1 - prob0, 3))
            await asyncio.sleep(1)
