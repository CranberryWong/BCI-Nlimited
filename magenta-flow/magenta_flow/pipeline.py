from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .midi_io import ArtifactPaths, ArtifactWriter, MidiOutput
from .transcription import StreamingMonophonicTranscriber, TranscriberConfig


@dataclass(frozen=True)
class GeneratedFrame:
    index: int
    samples: np.ndarray
    model_ms: float


@dataclass(frozen=True)
class ProducerError:
    error: BaseException


_END = object()


def validate_resources(magenta_home: Path, model_name: str) -> list[Path]:
    required = [
        magenta_home / "models" / model_name / f"{model_name}.mlxfn",
        magenta_home / "models" / model_name / f"{model_name}_state.safetensors",
        magenta_home / "resources" / "musiccoca" / "spm.model",
        magenta_home / "resources" / "musiccoca" / "text_encoder.tflite",
        magenta_home / "resources" / "musiccoca" / "mapper.tflite",
        magenta_home / "resources" / "spectrostream" / "decoder.safetensors",
        magenta_home / "resources" / "spectrostream" / "quantizer.safetensors",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        formatted = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(f"Missing MRT2 resources:\n{formatted}")
    return required


class MagentaFrameProducer(threading.Thread):
    """Own all MLX inference on one producer thread."""

    def __init__(
        self,
        output: queue.Queue,
        stop: threading.Event,
        magenta_home: Path,
        model_name: str,
        prompt: str,
        duration: float,
        temperature: float,
        top_k: int,
        style_strength: float,
    ):
        super().__init__(name="mrt2-producer", daemon=True)
        self.output = output
        self.stop = stop
        self.magenta_home = magenta_home
        self.model_name = model_name
        self.prompt = prompt
        self.duration = duration
        self.temperature = temperature
        self.top_k = top_k
        self.style_strength = style_strength

    def run(self) -> None:
        try:
            from magenta_rt import MagentaRT2StdMlxfn, paths
            from magenta_rt.config import MUSICCOCA

            paths.set_magenta_home(self.magenta_home)
            model = MagentaRT2StdMlxfn(
                size=self.model_name,
                temperature=self.temperature,
                top_k=self.top_k,
                cfg_scales={
                    "musiccoca": self.style_strength,
                    "notes": 1.0,
                    "drums": 0.0,
                },
            )
            style = model.embed_style(self.prompt, use_mapper=True)
            state = None
            max_frames = None if self.duration == 0 else round(self.duration * 25)
            index = 0
            while not self.stop.is_set() and (
                max_frames is None or index < max_frames
            ):
                started = time.perf_counter()
                waveform, state = model.generate(
                    conditioning={MUSICCOCA.key: style},
                    frames=1,
                    state=state,
                )
                elapsed_ms = (time.perf_counter() - started) * 1_000.0
                samples = np.asarray(waveform.samples, dtype=np.float32)
                self._put(GeneratedFrame(index, samples, elapsed_ms))
                index += 1
        except BaseException as exc:  # forwarded to the controlling thread
            self._put(ProducerError(exc))
        finally:
            self._put(_END)

    def _put(self, value: object) -> None:
        while not self.stop.is_set():
            try:
                self.output.put(value, timeout=0.1)
                return
            except queue.Full:
                continue


@dataclass(frozen=True)
class RunSummary:
    frames: int
    midi_events: int
    queue_underruns: int
    average_model_ms: float
    maximum_model_ms: float
    artifacts: ArtifactPaths


def prepare_audio_block(
    samples: np.ndarray, expected_shape: tuple[int, int]
) -> np.ndarray:
    """Validate a model frame and make it safe for PortAudio."""
    if samples.shape != expected_shape:
        raise ValueError(
            f"MRT2 returned {samples.shape}, expected {expected_shape}"
        )
    return np.ascontiguousarray(samples, dtype=np.float32)


def run_pipeline(
    *,
    magenta_home: Path,
    model_name: str,
    prompt: str,
    duration: float,
    temperature: float,
    top_k: int,
    style_strength: float,
    midi_output: MidiOutput,
    output_dir: Path,
    midi_channel: int,
    play_audio: bool,
    prebuffer_frames: int = 5,
) -> RunSummary:
    config = TranscriberConfig()
    transcriber = StreamingMonophonicTranscriber(config)
    artifacts = ArtifactWriter(output_dir, config.sample_rate, channels=2)
    frame_queue: queue.Queue = queue.Queue(maxsize=12)
    stop = threading.Event()
    producer = MagentaFrameProducer(
        frame_queue,
        stop,
        magenta_home,
        model_name,
        prompt,
        duration,
        temperature,
        top_k,
        style_strength,
    )

    audio_stream = None
    model_times: list[float] = []
    event_count = 0
    frame_count = 0
    underruns = 0
    start_time = time.monotonic()

    try:
        producer.start()
        _wait_for_prebuffer(frame_queue, producer, prebuffer_frames)
        if play_audio:
            import sounddevice as sd

            audio_stream = sd.OutputStream(
                samplerate=config.sample_rate,
                channels=2,
                dtype="float32",
                blocksize=config.block_size,
            )
            audio_stream.start()

        while True:
            try:
                item = frame_queue.get(timeout=0.12)
            except queue.Empty:
                if not producer.is_alive():
                    break
                underruns += 1
                continue

            if item is _END:
                break
            if isinstance(item, ProducerError):
                raise RuntimeError("MRT2 generation failed") from item.error
            assert isinstance(item, GeneratedFrame)

            # MRT2 constructs Waveform.samples by transposing a (2, T) model
            # output. That view has the right shape but is not C-contiguous,
            # while sounddevice.OutputStream.write requires contiguous memory.
            samples = prepare_audio_block(
                item.samples, (config.block_size, 2)
            )

            timestamp = item.index / 25.0
            artifacts.write_audio(samples)
            for event in transcriber.process_block(samples, timestamp):
                midi_output.send(event)
                artifacts.write_event(event)
                event_count += 1

            if audio_stream is not None:
                audio_stream.write(samples)
            else:
                target = start_time + (item.index + 1) / 25.0
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)

            model_times.append(item.model_ms)
            frame_count += 1
    except KeyboardInterrupt:
        stop.set()
    finally:
        stop.set()
        final_timestamp = frame_count / 25.0
        for event in transcriber.flush(final_timestamp):
            midi_output.send(event)
            artifacts.write_event(event)
            event_count += 1
        midi_output.close()
        if audio_stream is not None:
            audio_stream.stop()
            audio_stream.close()
        producer.join(timeout=3)
        paths = artifacts.close(midi_channel)

    return RunSummary(
        frames=frame_count,
        midi_events=event_count,
        queue_underruns=underruns,
        average_model_ms=float(np.mean(model_times)) if model_times else 0.0,
        maximum_model_ms=max(model_times, default=0.0),
        artifacts=paths,
    )


def _wait_for_prebuffer(
    frame_queue: queue.Queue,
    producer: threading.Thread,
    requested_frames: int,
) -> None:
    while producer.is_alive() and frame_queue.qsize() < requested_frames:
        time.sleep(0.01)
