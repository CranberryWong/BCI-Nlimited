from __future__ import annotations

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


def valence_arousal_handler(address: str, *args) -> None:
    print(f"Received OSC -> address: {address}, payload: {args}")


def run_validation_server(port: int = 8000, address: str = "/eeg/valence_arousal") -> None:
    dispatcher = Dispatcher()
    dispatcher.map(address, valence_arousal_handler)
    server = BlockingOSCUDPServer(("0.0.0.0", int(port)), dispatcher)
    print(f"OSC validation server listening on 0.0.0.0:{port} for {address}")
    server.serve_forever()

