from __future__ import annotations

from collections.abc import Awaitable, Callable

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer


OscCallback = Callable[[int, int, float, float], Awaitable[None]]


class OscInputServer:
    def __init__(self, ip: str, port: int, on_payload: OscCallback) -> None:
        self.ip = ip
        self.port = port
        self.on_payload = on_payload
        self.transport = None
        self.protocol = None

    @property
    def running(self) -> bool:
        return self.transport is not None

    async def start(self) -> None:
        if self.running:
            return
        dispatcher = Dispatcher()
        dispatcher.map("/eeg/valence_arousal", self._handle_payload)
        server = AsyncIOOSCUDPServer((self.ip, self.port), dispatcher, __import__("asyncio").get_running_loop())
        self.transport, self.protocol = await server.create_serve_endpoint()

    async def stop(self) -> None:
        if self.transport:
            self.transport.close()
        self.transport = None
        self.protocol = None

    def _handle_payload(self, _address: str, *args) -> None:
        if len(args) < 4:
            return
        import asyncio

        asyncio.create_task(self.on_payload(int(args[0]), int(args[1]), float(args[2]), float(args[3])))
