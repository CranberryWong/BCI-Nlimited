from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_control, routes_music, routes_outputs, routes_sessions, routes_tracks
from app.core.config import get_settings
from app.core.process_manager import ProcessManager
from app.core.websocket_manager import WebSocketManager
from app.music.config_loader import MusicConfigStore
from app.music.engine import MusicEngine
from app.music.midi_output import MidiOutput
from app.music.osc_output import OscOutput
from app.music.recorder import SessionRecorder
from app.storage.presets import PresetStore


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.websocket = WebSocketManager()
    app.state.config_store = MusicConfigStore(settings.music_defaults_path)
    app.state.midi = MidiOutput()
    app.state.osc = OscOutput(settings.default_output_osc_ip, settings.default_output_osc_port)
    app.state.recorder = SessionRecorder(settings.session_dir)
    app.state.presets = PresetStore(settings.preset_dir)
    app.state.engine = MusicEngine(app.state.config_store.active_config, app.state.midi, app.state.osc)
    app.state.runtime = ProcessManager(settings, app.state.websocket, app.state.config_store, app.state.engine, app.state.recorder)
    await app.state.runtime.startup()
    yield
    await app.state.runtime.shutdown()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_control.router)
app.include_router(routes_tracks.router)
app.include_router(routes_outputs.router)
app.include_router(routes_sessions.router)
app.include_router(routes_music.router)


@app.get("/api/health")
def health():
    return {"ok": True, "input_osc_port": settings.bci_input_osc_port}


@app.websocket("/ws/realtime")
async def realtime(websocket: WebSocket):
    await websocket.app.state.websocket.connect(websocket)
    await websocket.send_json({"kind": "status", "status": websocket.app.state.runtime.status()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket.app.state.websocket.disconnect(websocket)
