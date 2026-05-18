from __future__ import annotations

import random
import threading
import time
from typing import Callable

SampleCallback = Callable[[int, int, float, float, str], None]


class FakeStreamRunner:
    def __init__(self, on_sample: SampleCallback, interval: float = 1.0) -> None:
        self.on_sample = on_sample
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            valence = random.randint(1, 9)
            arousal = random.randint(1, 9)
            prob0 = round(random.uniform(0.1, 0.9), 2)
            prob1 = round(1 - prob0, 2)
            self.on_sample(valence, arousal, prob0, prob1, "test")
            self._stop_event.wait(self.interval)

