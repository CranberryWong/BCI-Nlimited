from __future__ import annotations

import time
from collections.abc import Callable

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer

from .schemas import InputSample


class SensorOscServer:
    """Vendor-neutral OSC adapter for heart rate, motion, light and posture."""

    def __init__(self, host: str, port: int, ingest: Callable[[InputSample], bool]) -> None:
        self.host = host
        self.port = port
        self.ingest = ingest
        self.transport = None
        self.protocol = None
        self.sequence = 0
        self.detail = "ready"

    @property
    def running(self) -> bool:
        return self.transport is not None

    async def start(self) -> None:
        if self.running:
            return
        dispatcher = Dispatcher()
        dispatcher.map("/v1/input/heart_rate", self._heart_rate)
        dispatcher.map("/v1/input/motion", self._motion)
        dispatcher.map("/v1/input/light", self._light)
        dispatcher.map("/v1/input/posture", self._posture)
        server = AsyncIOOSCUDPServer((self.host, self.port), dispatcher, __import__("asyncio").get_running_loop())
        self.transport, self.protocol = await server.create_serve_endpoint()
        self.detail = "running"

    async def stop(self) -> None:
        if self.transport:
            self.transport.close()
        self.transport = None
        self.protocol = None
        self.detail = "stopped"

    def _sample(self, kind: str, values: dict, quality: float) -> None:
        self.sequence += 1
        self.ingest(InputSample(
            source_id=f"sensor.{kind}",
            kind=kind,
            timestamp=time.time(),
            sequence=self.sequence,
            quality=max(0.0, min(1.0, quality)),
            values=values,
        ))

    def _heart_rate(self, _address: str, *args) -> None:
        if args:
            self._sample("heart_rate", {"bpm": float(args[0])}, float(args[1]) if len(args) > 1 else 1.0)

    def _motion(self, _address: str, *args) -> None:
        if args:
            self._sample("motion", {"intensity": float(args[0]), "cadence": float(args[1]) if len(args) > 1 else 0.0}, float(args[2]) if len(args) > 2 else 1.0)

    def _light(self, _address: str, *args) -> None:
        if args:
            self._sample("light", {"lux": float(args[0])}, float(args[1]) if len(args) > 1 else 1.0)

    def _posture(self, _address: str, *args) -> None:
        if len(args) < 3:
            return
        self._sample("posture", {
            "expansion": float(args[0]),
            "symmetry": float(args[1]),
            "verticality": float(args[2]),
            "gesture": str(args[3]) if len(args) > 3 else "",
        }, float(args[4]) if len(args) > 4 else 1.0)
