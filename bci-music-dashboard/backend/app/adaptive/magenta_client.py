from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

import websockets


EventCallback = Callable[[dict[str, Any]], Awaitable[None]]
LogCallback = Callable[[str, str, dict[str, Any]], None]


class MagentaWorkerClient:
    def __init__(self, url: str, on_event: EventCallback, log: LogCallback, command: list[str] | None = None, cwd: Path | None = None) -> None:
        self.url = url
        self.on_event = on_event
        self.log = log
        self.task: asyncio.Task | None = None
        self.sender_task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()
        self.commands: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=4)
        self.connected = False
        self.status_detail = "not_started"
        self.health: dict[str, Any] = {}
        self.failures = 0
        self.command = command or []
        self.cwd = cwd
        self.process: asyncio.subprocess.Process | None = None

    async def start(
        self,
        prompt: str,
        audio_enabled: bool,
        audio_gain: float,
        audio_device=None,
        artifact_dir: Path | None = None,
        transcription: dict[str, Any] | None = None,
    ) -> None:
        if self.task and not self.task.done():
            return
        self.stop_event.clear()
        if self.command and (self.process is None or self.process.returncode is not None):
            try:
                command = list(self.command)
                if artifact_dir is not None:
                    command.extend(["--output-dir", str(artifact_dir / "magenta")])
                self.process = await asyncio.create_subprocess_exec(
                    *command,
                    cwd=str(self.cwd) if self.cwd else None,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                self.status_detail = "worker_starting"
                await asyncio.sleep(0.35)
            except Exception as exc:
                self.status_detail = f"worker start failed: {exc}"
                self.log("warning", "Magenta worker process could not start", {"error": str(exc)})
        self.task = asyncio.create_task(
            self._run(prompt, audio_enabled, audio_gain, audio_device, transcription),
            name="magenta-worker-client",
        )

    async def stop(self) -> None:
        self.stop_event.set()
        await self._enqueue({"v": 1, "type": "stop"})
        if self.task:
            try:
                await asyncio.wait_for(self.task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.task.cancel()
        self.task = None
        self.connected = False
        self.status_detail = "stopped"
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        self.process = None

    async def update_conditioning(
        self,
        pianoroll: list[int],
        prompt: str | None = None,
        audio_gain: float | None = None,
        stem_path: str | None = None,
        stem_gain: float | None = None,
        stem_crossfade_seconds: float | None = None,
    ) -> None:
        command: dict[str, Any] = {"v": 1, "type": "condition", "pianoroll": pianoroll, "sent_at": time.time()}
        if prompt:
            command["prompt"] = prompt
        if audio_gain is not None:
            command["audio_gain"] = audio_gain
        if stem_path is not None:
            command["stem_path"] = stem_path
        if stem_gain is not None:
            command["stem_gain"] = stem_gain
        if stem_crossfade_seconds is not None:
            command["stem_crossfade_seconds"] = stem_crossfade_seconds
        await self._enqueue(command)

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "detail": self.status_detail,
            "failures": self.failures,
            "health": self.health,
            "url": self.url,
        }

    async def _run(
        self,
        prompt: str,
        audio_enabled: bool,
        audio_gain: float,
        audio_device=None,
        transcription: dict[str, Any] | None = None,
    ) -> None:
        self.status_detail = "connecting"
        try:
            websocket = None
            for attempt in range(10):
                try:
                    websocket = await websockets.connect(self.url, open_timeout=0.5, close_timeout=0.5, max_size=2**20)
                    break
                except Exception:
                    if attempt == 9:
                        raise
                    await asyncio.sleep(0.25)
            assert websocket is not None
            async with websocket:
                self.connected = True
                self.status_detail = "ready"
                await websocket.send(json.dumps({
                    "v": 1,
                    "type": "start",
                    "prompt": prompt,
                    "audio_enabled": audio_enabled,
                    "audio_gain": audio_gain,
                    "audio_device": audio_device,
                    "transcription": transcription or {},
                }))
                self.sender_task = asyncio.create_task(self._sender(websocket), name="magenta-worker-sender")
                async for raw in websocket:
                    message = json.loads(raw)
                    kind = message.get("type")
                    if kind == "note":
                        await self.on_event(message)
                    elif kind == "health":
                        self.health = message
                    elif kind == "error":
                        self.status_detail = str(message.get("detail", "worker error"))
                        self.log("error", "Magenta worker error", message)
                    if self.stop_event.is_set():
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failures += 1
            self.status_detail = f"unavailable: {exc}"
            self.log("warning", "Magenta worker unavailable; using motif fallback", {"error": str(exc)})
        finally:
            self.connected = False
            if self.sender_task:
                self.sender_task.cancel()
            self.sender_task = None

    async def _sender(self, websocket) -> None:
        while not self.stop_event.is_set():
            command = await self.commands.get()
            await websocket.send(json.dumps(command))
            if command.get("type") == "stop":
                return

    async def _enqueue(self, command: dict[str, Any]) -> None:
        if self.commands.full():
            try:
                self.commands.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self.commands.put(command)
