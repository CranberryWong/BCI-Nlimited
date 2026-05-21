from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app.bci.emotion_mapper import EmotionMapper
from app.bci.model_runner import ModelRunner
from app.bci.osc_input import OscInputServer
from app.bci.simulator_runner import SimulatorRunner
from app.bci.xdf_watcher import XdfWatcher
from app.core.config import Settings
from app.core.websocket_manager import WebSocketManager
from app.music.config_loader import MusicConfigStore
from app.music.engine import MusicEngine
from app.music.recorder import SessionRecorder
from app.music.schemas import EmotionState, MusicEvent


class ProcessManager:
    def __init__(
        self,
        settings: Settings,
        websocket: WebSocketManager,
        config_store: MusicConfigStore,
        engine: MusicEngine,
        recorder: SessionRecorder,
    ) -> None:
        self.settings = settings
        self.websocket = websocket
        self.config_store = config_store
        self.engine = engine
        self.recorder = recorder
        self.mapper = EmotionMapper()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.latest_emotion: EmotionState | None = None
        self.latest_events: list[MusicEvent] = []
        self.model_runner = ModelRunner(settings.resolved_model_path, self._thread_model_payload)
        self.watcher: XdfWatcher | None = None
        self.simulator = SimulatorRunner(lambda *payload: self.process_payload(*payload, source="simulator"))
        self.osc_input = OscInputServer(settings.bci_input_osc_ip, settings.bci_input_osc_port, lambda *payload: self.process_payload(*payload, source="osc_input"))
        self.osc_input_detail = "ready"
        self.model_detail = "model_missing" if not self.model_runner.available else "ready"

    async def startup(self) -> None:
        self.loop = asyncio.get_running_loop()
        try:
            await self.osc_input.start()
            self.osc_input_detail = "running"
        except OSError as exc:
            self.osc_input_detail = f"unavailable: {exc}"

    async def shutdown(self) -> None:
        await self.simulator.stop()
        self.stop_model()
        await self.osc_input.stop()

    async def process_payload(self, valence: int, arousal: int, prob0: float, prob1: float, source: str) -> None:
        emotion = self.mapper.from_tuple(valence, arousal, prob0, prob1, source=source)
        events = self.engine.generate(emotion)
        self.latest_emotion = emotion
        self.latest_events = events
        self.recorder.record_emotion(emotion)
        for event in events:
            self.recorder.record_event(event)
        await self.websocket.broadcast(
            {
                "kind": "realtime",
                "emotion": emotion.model_dump(),
                "music_events": [event.model_dump() for event in events],
                "status": self.status(),
            }
        )

    def status(self) -> dict[str, Any]:
        return {
            "model_status": "running" if self.watcher and self.watcher.running else self.model_detail,
            "model_available": self.model_runner.available,
            "simulator_running": self.simulator.running,
            "osc_input_running": self.osc_input.running,
            "osc_input_status": self.osc_input_detail,
            "osc_input": f"{self.settings.bci_input_osc_ip}:{self.settings.bci_input_osc_port}",
            "recording_session_id": self.recorder.active_id,
            "latest_source": self.latest_emotion.source if self.latest_emotion else None,
        }

    def start_model(self) -> dict[str, Any]:
        if not self.model_runner.available:
            self.model_detail = "model_missing"
            raise FileNotFoundError(f"place the model at {self.model_runner.model_path}")
        if self.settings.resolved_xdf_root_dir is None:
            raise ValueError("XDF_ROOT_DIR is required to start the real model watcher")
        self.model_runner.load()
        self.watcher = self.watcher or XdfWatcher(Path(self.settings.resolved_xdf_root_dir), self.model_runner)
        self.watcher.start()
        self.model_detail = "running"
        return self.status()

    def stop_model(self) -> dict[str, Any]:
        if self.watcher:
            self.watcher.stop()
        self.model_detail = "ready" if self.model_runner.available else "model_missing"
        return self.status()

    def apply_config(self) -> None:
        self.engine.update_config(self.config_store.active_config)

    def _thread_model_payload(self, valence: int, arousal: int, prob0: float, prob1: float) -> None:
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self.process_payload(valence, arousal, prob0, prob1, source="real_model"),
                self.loop,
            )
