from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import websockets

from .midi_io import ArtifactWriter
from .pipeline import prepare_audio_block, validate_resources
from .transcription import StreamingMonophonicTranscriber, TranscriberConfig


DEFAULT_HOME = Path.home() / "Documents" / "Magenta" / "magenta-rt-v2"


@dataclass
class WorkerControl:
    running: bool = True
    prompt: str = "Flowing solo marimba improvisation, single clear notes"
    pending_prompt: str | None = None
    pianoroll: list[int] = field(default_factory=lambda: [0] * 128)
    audio_enabled: bool = True
    audio_gain: float = 0.2
    stem_path: str | None = None
    stem_gain: float = 0.0
    stem_crossfade_seconds: float = 4.0


class StemLoopMixer:
    def __init__(self, sample_rate: int, crossfade_seconds: float = 4.0) -> None:
        self.sample_rate = sample_rate
        self.samples: np.ndarray | None = None
        self.position = 0
        self.path = ""
        self.previous_samples: np.ndarray | None = None
        self.previous_position = 0
        self.crossfade_samples = max(1, round(sample_rate * crossfade_seconds))
        self.crossfade_position = self.crossfade_samples

    def set_crossfade(self, seconds: float) -> None:
        self.crossfade_samples = max(1, round(self.sample_rate * max(0.01, seconds)))

    def load(self, path: str | None) -> None:
        if not path or path == self.path:
            return
        values, rate = sf.read(path, dtype="float32", always_2d=True)
        if rate != self.sample_rate:
            raise ValueError(f"stem sample rate must be {self.sample_rate}, got {rate}")
        if values.shape[1] == 1:
            values = np.repeat(values, 2, axis=1)
        if len(values) == 0:
            raise ValueError("stem file is empty")
        self.previous_samples = self.samples
        self.previous_position = self.position
        self.samples = np.ascontiguousarray(values[:, :2], dtype=np.float32)
        self.position = 0
        self.path = path
        self.crossfade_position = 0 if self.previous_samples is not None else self.crossfade_samples

    def mix(self, block: np.ndarray, gain: float) -> np.ndarray:
        if self.samples is None or gain <= 0:
            return block
        output = np.array(block, dtype=np.float32, copy=True)
        current = self._next(self.samples, "position", len(output))
        stem = current
        if self.previous_samples is not None and self.crossfade_position < self.crossfade_samples:
            previous = self._next(self.previous_samples, "previous_position", len(output))
            start = self.crossfade_position
            weights = np.clip((np.arange(len(output)) + start) / self.crossfade_samples, 0.0, 1.0).astype(np.float32)[:, None]
            stem = previous * (1.0 - weights) + current * weights
            self.crossfade_position += len(output)
            if self.crossfade_position >= self.crossfade_samples:
                self.previous_samples = None
        output += stem * gain
        return np.clip(output, -0.98, 0.98)

    def _next(self, samples: np.ndarray, position_name: str, size: int) -> np.ndarray:
        output = np.zeros((size, 2), dtype=np.float32)
        position = int(getattr(self, position_name))
        remaining = size
        offset = 0
        while remaining:
            count = min(remaining, len(samples) - position)
            output[offset:offset + count] = samples[position:position + count]
            position = (position + count) % len(samples)
            offset += count
            remaining -= count
        setattr(self, position_name, position)
        return output


class MagentaWorkerServer:
    def __init__(self, magenta_home: Path, model_name: str, output_dir: Path) -> None:
        self.magenta_home = magenta_home
        self.model_name = model_name
        self.output_dir = output_dir
        self.active = False

    async def handler(self, websocket) -> None:
        if self.active:
            await websocket.send(json.dumps({"v": 1, "type": "error", "detail": "worker already has an active client"}))
            await websocket.close(code=1013, reason="busy")
            return
        self.active = True
        control = WorkerControl()
        receiver: asyncio.Task | None = None
        artifacts: ArtifactWriter | None = None
        audio_stream = None
        transcriber: StreamingMonophonicTranscriber | None = None
        frame_index = 0
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            command = json.loads(raw)
            if command.get("v") != 1 or command.get("type") != "start":
                raise ValueError("first command must be v1 start")
            control.prompt = str(command.get("prompt") or control.prompt)
            control.audio_enabled = bool(command.get("audio_enabled", True))
            control.audio_gain = max(0.0, min(1.0, float(command.get("audio_gain", 0.2))))
            audio_device = command.get("audio_device")
            receiver = asyncio.create_task(self._receive(websocket, control), name="magenta-worker-receiver")

            validate_resources(self.magenta_home, self.model_name)
            from magenta_rt import MagentaRT2StdMlxfn, paths
            from magenta_rt.config import MUSICCOCA, PIANOROLL_WITH_ONSETS

            paths.set_magenta_home(self.magenta_home)
            model = MagentaRT2StdMlxfn(
                size=self.model_name,
                temperature=1.0,
                top_k=20,
                cfg_scales={"musiccoca": 2.4, "notes": 1.0, "drums": 0.0},
            )
            style = model.embed_style(control.prompt, use_mapper=True)
            state = None
            transcriber_config = TranscriberConfig()
            transcriber = StreamingMonophonicTranscriber(transcriber_config)
            artifacts = ArtifactWriter(self.output_dir, transcriber_config.sample_rate, channels=2)
            mixer = StemLoopMixer(transcriber_config.sample_rate)
            if control.audio_enabled:
                import sounddevice as sd

                audio_stream = sd.OutputStream(
                    samplerate=transcriber_config.sample_rate,
                    channels=2,
                    dtype="float32",
                    blocksize=transcriber_config.block_size,
                    device=audio_device,
                )
                audio_stream.start()

            model_times: list[float] = []
            start_monotonic = time.monotonic()
            await websocket.send(json.dumps({"v": 1, "type": "health", "status": "ready", "model": self.model_name, "frame_hz": 25}))
            while control.running:
                if control.pending_prompt:
                    style = model.embed_style(control.pending_prompt, use_mapper=True)
                    control.prompt = control.pending_prompt
                    control.pending_prompt = None
                if control.stem_path:
                    try:
                        mixer.set_crossfade(control.stem_crossfade_seconds)
                        mixer.load(control.stem_path)
                    except Exception as exc:
                        await websocket.send(json.dumps({"v": 1, "type": "error", "detail": f"stem load failed: {exc}"}))
                        control.stem_path = None
                        control.stem_gain = 0.0
                started = time.perf_counter()
                waveform, state = model.generate(
                    conditioning={
                        MUSICCOCA.key: style,
                        PIANOROLL_WITH_ONSETS.key: control.pianoroll,
                    },
                    frames=1,
                    state=state,
                )
                model_ms = (time.perf_counter() - started) * 1000.0
                samples = prepare_audio_block(np.asarray(waveform.samples, dtype=np.float32), (transcriber_config.block_size, 2))
                generated_at = time.time()
                artifacts.write_audio(samples)
                timestamp = frame_index / 25.0
                for event in transcriber.process_block(samples, timestamp):
                    artifacts.write_event(event)
                    await websocket.send(json.dumps({
                        "v": 1,
                        "type": "note",
                        "kind": event.kind,
                        "note": event.note,
                        "velocity": event.velocity,
                        "frequency": event.frequency,
                        "confidence": event.confidence,
                        "timestamp": event.timestamp,
                        "generated_at": generated_at,
                        "frame": frame_index,
                    }))
                if audio_stream is not None:
                    mixed = mixer.mix(samples * control.audio_gain, control.stem_gain)
                    audio_stream.write(np.ascontiguousarray(mixed, dtype=np.float32))
                model_times.append(model_ms)
                frame_index += 1
                if frame_index % 25 == 0:
                    recent = model_times[-100:]
                    await websocket.send(json.dumps({
                        "v": 1,
                        "type": "health",
                        "status": "running",
                        "frames": frame_index,
                        "average_model_ms": float(np.mean(recent)),
                        "maximum_model_ms": max(recent),
                        "analysis_latency_ms": transcriber.analysis_latency_ms,
                        "prompt": control.prompt,
                    }))
                target = start_monotonic + frame_index / 25.0
                await asyncio.sleep(max(0.0, target - time.monotonic()))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            try:
                await websocket.send(json.dumps({"v": 1, "type": "error", "detail": str(exc)}))
            except Exception:
                pass
        finally:
            control.running = False
            if receiver:
                receiver.cancel()
            if artifacts and transcriber is not None:
                for event in transcriber.flush(frame_index / 25.0):
                    artifacts.write_event(event)
                    try:
                        await websocket.send(json.dumps({
                            "v": 1, "type": "note", "kind": event.kind,
                            "note": event.note, "velocity": 0, "confidence": event.confidence,
                            "generated_at": time.time(),
                        }))
                    except Exception:
                        pass
                artifacts.close(1)
            if audio_stream is not None:
                audio_stream.stop()
                audio_stream.close()
            self.active = False

    async def _receive(self, websocket, control: WorkerControl) -> None:
        async for raw in websocket:
            command = json.loads(raw)
            if command.get("v") != 1:
                continue
            kind = command.get("type")
            if kind == "stop":
                control.running = False
                return
            if kind == "condition":
                pianoroll = command.get("pianoroll")
                if isinstance(pianoroll, list) and len(pianoroll) == 128:
                    control.pianoroll = [max(-1, min(3, int(value))) for value in pianoroll]
                if command.get("prompt") and command.get("prompt") != control.prompt:
                    control.pending_prompt = str(command["prompt"])
                if "audio_gain" in command:
                    control.audio_gain = max(0.0, min(1.0, float(command["audio_gain"])))
                if "stem_path" in command:
                    control.stem_path = str(command["stem_path"]) if command["stem_path"] else None
                    control.stem_gain = max(0.0, min(1.0, float(command.get("stem_gain", 0.0))))
                if "stem_crossfade_seconds" in command:
                    control.stem_crossfade_seconds = max(0.01, float(command["stem_crossfade_seconds"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local MRT2 WebSocket worker for BCI Music Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--magenta-home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--model", default="mrt2_small")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "outputs")
    return parser


async def serve(args: argparse.Namespace) -> None:
    server = MagentaWorkerServer(args.magenta_home, args.model, args.output_dir)
    async with websockets.serve(server.handler, args.host, args.port, max_size=2**20):
        await asyncio.Future()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
