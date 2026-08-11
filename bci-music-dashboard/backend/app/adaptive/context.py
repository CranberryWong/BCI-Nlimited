from __future__ import annotations

import asyncio
import json
import math
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .schemas import AdapterStatus, ContextFrame, InputSample


LogCallback = Callable[[str, str, dict[str, Any]], None]


class ContextHub:
    """Normalize asynchronous sensor samples without blocking the music loop."""

    def __init__(self, config: dict[str, Any], log: LogCallback | None = None) -> None:
        self.config = config
        self.log = log or (lambda _level, _message, _data: None)
        self.samples: dict[str, InputSample] = {}
        self.statuses: dict[str, AdapterStatus] = {}
        self.weather_task: asyncio.Task | None = None
        self.weather_failures = 0
        self.weather_circuit_until = 0.0
        self.last_weather_at: float | None = None

    async def start(self) -> None:
        bci_id = self.config.get("bci", {}).get("source_id", "bci.primary")
        self.statuses.setdefault(bci_id, AdapterStatus(source_id=bci_id, kind="bci", health="missing"))
        time_id = self.config.get("time", {}).get("source_id", "system.clock")
        self.statuses.setdefault(time_id, AdapterStatus(source_id=time_id, kind="time", health="missing"))
        for kind, source_ids in self.config.get("sensors", {}).get("accepted_sources", {}).items():
            for source_id in source_ids:
                self.statuses.setdefault(source_id, AdapterStatus(source_id=source_id, kind=kind, health="missing"))
        weather = self.config.get("weather", {})
        if weather.get("enabled") and weather.get("latitude") is not None and weather.get("longitude") is not None:
            self.weather_task = asyncio.create_task(self._weather_loop(), name="adaptive-weather")
        else:
            self.statuses[weather.get("source_id", "weather.open_meteo")] = AdapterStatus(
                source_id=weather.get("source_id", "weather.open_meteo"),
                kind="weather",
                health="disabled",
                detail="weather disabled or latitude/longitude not configured",
            )

    async def stop(self) -> None:
        if self.weather_task:
            self.weather_task.cancel()
            try:
                await self.weather_task
            except asyncio.CancelledError:
                pass
        self.weather_task = None

    def ingest(self, sample: InputSample) -> bool:
        previous = self.samples.get(sample.source_id)
        if previous and sample.sequence and previous.sequence and sample.sequence <= previous.sequence:
            self.log("warning", "discarded out-of-order input", {"source_id": sample.source_id, "sequence": sample.sequence})
            return False
        self.samples[sample.source_id] = sample
        self.statuses[sample.source_id] = AdapterStatus(
            source_id=sample.source_id,
            kind=sample.kind,
            health="healthy",
            last_sample_at=sample.timestamp,
            age_seconds=max(0.0, time.time() - sample.timestamp),
            quality=sample.quality,
        )
        return True

    def frame(self, now: float | None = None) -> ContextFrame:
        now = now or time.time()
        self._sample_clock(now)
        bci_id = self.config.get("bci", {}).get("source_id", "bci.primary")
        bci = self.samples.get(bci_id)
        bci_stale_after = float(self.config.get("bci", {}).get("stale_after_seconds", 5))
        valence, arousal, confidence = 0.5, 0.5, 0.0
        bci_age = None
        degraded = True
        if bci:
            bci_age = max(0.0, now - bci.timestamp)
            degraded = bci_age > bci_stale_after
            confidence = bci.quality * self._unit(bci.values.get("confidence", bci.quality))
            if not degraded:
                valence = self._unit(bci.values.get("valence", 0.5))
                arousal = self._unit(bci.values.get("arousal", 0.5))
            else:
                hold = bci_stale_after
                return_seconds = max(0.1, float(self.config.get("bci", {}).get("neutral_return_seconds", 10)))
                amount = min(1.0, max(0.0, (bci_age - hold) / return_seconds))
                valence = self._lerp(self._unit(bci.values.get("valence", 0.5)), 0.5, amount)
                arousal = self._lerp(self._unit(bci.values.get("arousal", 0.5)), 0.5, amount)
                confidence *= 1.0 - amount

        heart = self._latest_kind("heart_rate", now)
        motion = self._latest_kind("motion", now)
        light = self._latest_kind("light", now)
        posture = self._latest_kind("posture", now)
        weather = self._latest_kind("weather", now, stale_after=float(self.config.get("weather", {}).get("cache_ttl_seconds", 1800)))
        circadian, daylight = self._time_features()
        if light:
            lux = max(0.0, float(light.values.get("lux", 0.0)))
            daylight = min(1.0, math.log10(1.0 + lux) / 4.0)

        self._refresh_status_ages(now)
        return ContextFrame(
            timestamp=now,
            valence=valence,
            arousal=arousal,
            bci_confidence=confidence,
            bci_age_seconds=bci_age,
            heart_rate=self._optional_float(heart, "bpm"),
            motion=self._optional_unit(motion, "intensity"),
            cadence=self._optional_float(motion, "cadence"),
            ambient_light=self._optional_float(light, "lux"),
            daylight=daylight,
            circadian_energy=circadian,
            weather_brightness=self._unit(weather.values.get("brightness", 0.5)) if weather else 0.5,
            precipitation=max(0.0, float(weather.values.get("precipitation", 0.0))) if weather else 0.0,
            wind=max(0.0, float(weather.values.get("wind_speed", 0.0))) if weather else 0.0,
            posture_expansion=self._optional_unit(posture, "expansion"),
            posture_symmetry=self._optional_unit(posture, "symmetry"),
            posture_verticality=self._optional_unit(posture, "verticality"),
            gesture=str(posture.values.get("gesture")) if posture and posture.values.get("gesture") else None,
            degraded=degraded,
            sources={key: value.model_copy(deep=True) for key, value in self.statuses.items()},
        )

    def public_status(self) -> list[dict[str, Any]]:
        self._refresh_status_ages(time.time())
        return [status.model_dump() for status in sorted(self.statuses.values(), key=lambda item: item.source_id)]

    async def _weather_loop(self) -> None:
        refresh = max(30.0, float(self.config.get("weather", {}).get("refresh_seconds", 600)))
        while True:
            await self._refresh_weather()
            await asyncio.sleep(refresh)

    async def _refresh_weather(self) -> None:
        weather = self.config.get("weather", {})
        source_id = weather.get("source_id", "weather.open_meteo")
        now = time.time()
        if now < self.weather_circuit_until:
            self.statuses[source_id] = AdapterStatus(
                source_id=source_id, kind="weather", health="circuit_open",
                last_sample_at=self.last_weather_at, failure_count=self.weather_failures,
                detail=f"retry after {self.weather_circuit_until:.0f}",
            )
            return
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(self._fetch_weather, weather),
                timeout=float(weather.get("timeout_seconds", 1.5)),
            )
            current = payload.get("current", {})
            cloud = self._unit(float(current.get("cloud_cover", 50.0)) / 100.0)
            is_day = float(current.get("is_day", 1.0))
            sample = InputSample(
                source_id=source_id,
                kind="weather",
                timestamp=now,
                sequence=int(now),
                quality=1.0,
                values={
                    "temperature": current.get("temperature_2m"),
                    "relative_humidity": current.get("relative_humidity_2m"),
                    "is_day": is_day,
                    "precipitation": current.get("precipitation", 0.0),
                    "weather_code": current.get("weather_code"),
                    "cloud_cover": current.get("cloud_cover", 50.0),
                    "wind_speed": current.get("wind_speed_10m", 0.0),
                    "brightness": max(0.0, min(1.0, (0.75 * is_day) + (0.25 * (1.0 - cloud)))),
                },
            )
            self.ingest(sample)
            self.last_weather_at = now
            self.weather_failures = 0
            self.log("info", "weather refreshed", sample.values)
        except Exception as exc:
            self.weather_failures += 1
            threshold = int(weather.get("failures_before_open", 3))
            if self.weather_failures >= threshold:
                self.weather_circuit_until = now + float(weather.get("circuit_open_seconds", 600))
            self.statuses[source_id] = AdapterStatus(
                source_id=source_id, kind="weather", health="error",
                last_sample_at=self.last_weather_at, failure_count=self.weather_failures, detail=str(exc),
            )
            self.log("warning", "weather refresh failed", {"error": str(exc), "failures": self.weather_failures})

    @staticmethod
    def _fetch_weather(config: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode({
            "latitude": config["latitude"],
            "longitude": config["longitude"],
            "timezone": config.get("timezone", "auto"),
            "current": "temperature_2m,relative_humidity_2m,is_day,precipitation,weather_code,cloud_cover,wind_speed_10m",
        })
        request = urllib.request.Request(f"https://api.open-meteo.com/v1/forecast?{query}", headers={"User-Agent": "BCI-Music-Dashboard/1"})
        with urllib.request.urlopen(request, timeout=float(config.get("timeout_seconds", 1.5))) as response:
            return json.loads(response.read().decode("utf-8"))

    def _latest_kind(self, kind: str, now: float, stale_after: float | None = None) -> InputSample | None:
        candidates = [sample for sample in self.samples.values() if sample.kind == kind]
        if not candidates:
            return None
        sample = max(candidates, key=lambda item: item.timestamp)
        maximum = stale_after if stale_after is not None else float(self.config.get("sensors", {}).get("stale_after_seconds", 5))
        return sample if now - sample.timestamp <= maximum else None

    def _refresh_status_ages(self, now: float) -> None:
        sensor_stale = float(self.config.get("sensors", {}).get("stale_after_seconds", 5))
        weather_stale = float(self.config.get("weather", {}).get("cache_ttl_seconds", 1800))
        for source_id, status in self.statuses.items():
            if status.last_sample_at is None:
                continue
            status.age_seconds = max(0.0, now - status.last_sample_at)
            limit = weather_stale if status.kind == "weather" else sensor_stale
            if status.health == "healthy" and status.age_seconds > limit:
                status.health = "stale"

    @staticmethod
    def _time_features() -> tuple[float, float]:
        hour = datetime.now().hour + datetime.now().minute / 60.0
        daylight = max(0.0, math.sin(math.pi * (hour - 6.0) / 12.0)) if 6 <= hour <= 18 else 0.0
        circadian = max(0.0, min(1.0, 0.5 + 0.35 * math.sin(2 * math.pi * (hour - 9.0) / 24.0)))
        return circadian, daylight

    def _sample_clock(self, now: float) -> None:
        config = self.config.get("time", {})
        if not config.get("enabled", True):
            return
        local = datetime.fromtimestamp(now)
        self.ingest(InputSample(
            source_id=config.get("source_id", "system.clock"),
            kind="time",
            timestamp=now,
            sequence=int(now * 1000),
            quality=1.0,
            values={
                "hour": local.hour,
                "minute": local.minute,
                "weekday": local.weekday(),
                "timezone": str(local.astimezone().tzinfo),
            },
        ))

    @staticmethod
    def _unit(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5

    @classmethod
    def _optional_unit(cls, sample: InputSample | None, key: str) -> float | None:
        return cls._unit(sample.values.get(key)) if sample and sample.values.get(key) is not None else None

    @staticmethod
    def _optional_float(sample: InputSample | None, key: str) -> float | None:
        try:
            return float(sample.values[key]) if sample and sample.values.get(key) is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _lerp(a: float, b: float, amount: float) -> float:
        return a + (b - a) * amount
