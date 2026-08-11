from __future__ import annotations

import asyncio
import math
import random
import time
from collections.abc import Awaitable, Callable


SimulatorCallback = Callable[[float, float, float, float], Awaitable[None]]


class SimulatorRunner:
    """Produces a continuous, plausible Valence/Arousal signal for local demos."""

    TARGET_CENTERS = {
        "neutral": (5.0, 5.0),
        "calm": (7.0, 3.0),
        "joy": (7.0, 7.0),
        "tense": (3.0, 7.0),
        "sad": (3.0, 3.0),
    }
    ADJACENT_TARGETS = {
        "neutral": ("neutral", "calm", "joy", "tense", "sad"),
        "calm": ("calm", "neutral", "joy", "sad"),
        "joy": ("joy", "calm", "neutral", "tense"),
        "tense": ("tense", "neutral", "joy", "sad"),
        "sad": ("sad", "neutral", "calm", "tense"),
    }
    TARGET_INTERVAL_SECONDS = (8.0, 15.0)
    MEAN_REVERSION = 0.13
    NOISE_STDDEV = 0.075
    NOISE_CORRELATION = 0.35
    MAX_STEP_PER_SECOND = 0.32

    def __init__(self, on_payload: SimulatorCallback, rng: random.Random | None = None) -> None:
        self.on_payload = on_payload
        self.rng = rng or random.Random()
        self.task: asyncio.Task | None = None
        self.valence = 5.0
        self.arousal = 5.0
        self.target_valence = 5.0
        self.target_arousal = 5.0
        self.target_label = "neutral"
        self.next_target_at = 0.0

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
        self._reset_session(time.monotonic())
        while True:
            valence, arousal, prob0, prob1 = self._next_payload(time.monotonic())
            await self.on_payload(valence, arousal, prob0, prob1)
            await asyncio.sleep(1)

    async def _run_past(self) -> None:
        """Previous independent-per-second random algorithm, retained for comparison."""
        while True:
            valence = random.randint(1, 9)
            arousal = random.randint(1, 9)
            prob0 = round(random.uniform(0.1, 0.9), 3)
            await self.on_payload(valence, arousal, prob0, round(1 - prob0, 3))
            await asyncio.sleep(1)

    def _reset_session(self, now: float) -> None:
        self.valence = 5.0
        self.arousal = 5.0
        self.target_valence = 5.0
        self.target_arousal = 5.0
        self.target_label = "neutral"
        self.next_target_at = now + self.rng.uniform(*self.TARGET_INTERVAL_SECONDS)

    def _next_payload(self, now: float) -> tuple[float, float, float, float]:
        if now >= self.next_target_at:
            self._choose_next_target(now)

        shared_noise = self.rng.gauss(0.0, self.NOISE_STDDEV)
        independent_noise = self.rng.gauss(0.0, self.NOISE_STDDEV)
        valence_noise = shared_noise
        arousal_noise = (
            self.NOISE_CORRELATION * shared_noise
            + math.sqrt(1 - self.NOISE_CORRELATION ** 2) * independent_noise
        )
        next_valence = self.valence + self.MEAN_REVERSION * (self.target_valence - self.valence) + valence_noise
        next_arousal = self.arousal + self.MEAN_REVERSION * (self.target_arousal - self.arousal) + arousal_noise
        valence_step = self._bounded_step(next_valence - self.valence)
        arousal_step = self._bounded_step(next_arousal - self.arousal)
        self.valence = self._clamp_axis(self.valence + valence_step)
        self.arousal = self._clamp_axis(self.arousal + arousal_step)

        distance_to_target = min(1.0, math.hypot(self.target_valence - self.valence, self.target_arousal - self.arousal) / 5.66)
        movement = max(abs(valence_step), abs(arousal_step)) / self.MAX_STEP_PER_SECOND
        confidence = min(0.96, max(0.55, 0.94 - 0.20 * distance_to_target - 0.12 * movement + self.rng.gauss(0.0, 0.015)))
        return self.valence, self.arousal, confidence, 1 - confidence

    def _choose_next_target(self, now: float) -> None:
        self.target_label = self.rng.choice(self.ADJACENT_TARGETS[self.target_label])
        center_valence, center_arousal = self.TARGET_CENTERS[self.target_label]
        self.target_valence = self._clamp_axis(center_valence + self.rng.gauss(0.0, 0.45))
        self.target_arousal = self._clamp_axis(center_arousal + self.rng.gauss(0.0, 0.45))
        self.next_target_at = now + self.rng.uniform(*self.TARGET_INTERVAL_SECONDS)

    def _bounded_step(self, value: float) -> float:
        return max(-self.MAX_STEP_PER_SECOND, min(self.MAX_STEP_PER_SECOND, value))

    @staticmethod
    def _clamp_axis(value: float) -> float:
        return max(1.0, min(9.0, value))
