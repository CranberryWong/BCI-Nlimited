from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from server.config import AppConfig
from server.pipeline.emotion import probabilities_to_emotion
from server.state import StateStore

SampleCallback = Callable[[int, int, float | None, float | None, str], None]


class XdfDataHandler:
    @staticmethod
    def parse_xdf(file_path: str):
        try:
            import pyxdf

            if not os.path.exists(file_path):
                return None
            data, header = pyxdf.load_xdf(file_path, verbose=False)
            return header, data
        except Exception as exc:
            print(f"[XDF] Parse failed for {file_path}: {exc}")
            return None


class EegInference:
    window_size = 300
    max_packets_per_window = 6
    expected_channels = 19
    min_pred_interval = 1.0

    def __init__(self, model_path: str, state: StateStore, on_sample: SampleCallback) -> None:
        self.model_path = Path(model_path)
        self.state = state
        self.on_sample = on_sample
        self.model = None
        self.eeg_buffer: list[np.ndarray] = []
        self.last_pred_time = -1e9

    def load_model(self) -> bool:
        if self.model is not None:
            return True
        if not self.model_path.exists():
            self.state.error(f"Model not found: {self.model_path}")
            return False
        try:
            import joblib

            self.model = joblib.load(self.model_path)
            self.state.patch(model_loaded=True)
            return True
        except Exception as exc:
            self.state.error(f"Model load failed: {exc}")
            return False

    def read_eeg_packet(self, file_path: Path) -> None:
        if not self.load_model():
            return
        xdf_result = XdfDataHandler.parse_xdf(str(file_path))
        if not xdf_result:
            return
        _header, data = xdf_result
        eeg_segment = np.asarray(data[0]["time_series"])
        eeg_segment = self._filter_channels(eeg_segment, data)
        if eeg_segment.shape[1] > self.expected_channels:
            eeg_segment = eeg_segment[:, : self.expected_channels]
        elif eeg_segment.shape[1] < self.expected_channels:
            self.state.log(
                f"Skipped EEG packet with {eeg_segment.shape[1]} channels; expected {self.expected_channels}"
            )
            return

        self.eeg_buffer.append(eeg_segment)
        if len(self.eeg_buffer) > self.max_packets_per_window * 2:
            self.eeg_buffer.pop(0)
        total_len = sum(seg.shape[0] for seg in self.eeg_buffer[-self.max_packets_per_window :])
        if total_len < self.window_size:
            return
        now = time.monotonic()
        if now - self.last_pred_time < self.min_pred_interval:
            return

        concat = np.concatenate(self.eeg_buffer[-self.max_packets_per_window :], axis=0)
        if concat.shape[0] > self.window_size:
            concat = concat[-self.window_size :, :]
        mean = concat.mean(axis=0, keepdims=True)
        std = concat.std(axis=0, keepdims=True) + 1e-6
        window_norm = (concat - mean) / std
        probs = self.model.predict_proba(window_norm.reshape(1, -1))
        prob0, prob1 = float(probs[0, 0]), float(probs[0, 1])
        valence, arousal = probabilities_to_emotion(prob0, prob1)
        self.on_sample(valence, arousal, prob0, prob1, "xdf")
        self.last_pred_time = now
        self.eeg_buffer.clear()

    def read_eye_packet(self, file_path: Path) -> None:
        xdf_result = XdfDataHandler.parse_xdf(str(file_path))
        if not xdf_result:
            return
        _header, data = xdf_result
        self.state.log(f"Eye packet: {np.asarray(data[0]['time_series']).shape}")

    @staticmethod
    def _filter_channels(eeg_segment: np.ndarray, data) -> np.ndarray:
        exclude_labels = {"A1", "A2", "X3", "X2", "X1", "TRG"}
        try:
            channels = data[0]["info"]["desc"][0]["channels"][0]["channel"]
            labels = [ch["label"][0] for ch in channels]
            keep_mask = np.array([label not in exclude_labels for label in labels], dtype=bool)
            return eeg_segment[:, keep_mask]
        except Exception:
            return eeg_segment


class XdfHandler(FileSystemEventHandler):
    def __init__(self, packet_queue: "queue.Queue[tuple[str, Path]]") -> None:
        super().__init__()
        self.packet_queue = packet_queue

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        parts = file_path.parts
        if "amplifier" in parts:
            self.packet_queue.put(("eeg", file_path))
        elif "eye_tracker" in parts:
            self.packet_queue.put(("eye", file_path))


class RealStreamWatcher:
    def __init__(self, config: AppConfig, state: StateStore, on_sample: SampleCallback) -> None:
        self.config = config
        self.state = state
        self.on_sample = on_sample
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._observer: Observer | None = None
        self._session_threads: list[threading.Thread] = []

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._watch_root, daemon=True)
        self._thread.start()
        self.state.patch(running=True, mode="xdf", xdf_watching=True, finished=False)

    def stop(self) -> None:
        self._stop_event.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        self.state.patch(running=False, xdf_watching=False, finished=True)

    def _watch_root(self) -> None:
        root_dir = Path(self.config.xdf_root_dir).expanduser()
        root_dir.mkdir(parents=True, exist_ok=True)
        handler = _RootHandler(self)
        observer = Observer()
        self._observer = observer
        observer.schedule(handler, str(root_dir), recursive=False)
        observer.start()
        self.state.log(f"Watching root directory: {root_dir}")
        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        finally:
            observer.stop()
            observer.join()

    def start_session(self, session_dir: Path) -> None:
        thread = threading.Thread(target=self._session_worker, args=(session_dir,), daemon=True)
        self._session_threads.append(thread)
        thread.start()

    def _session_worker(self, session_dir: Path) -> None:
        xdf_dir = self._wait_for_xdf_dir(session_dir)
        if xdf_dir is None:
            return
        packet_queue: "queue.Queue[tuple[str, Path]]" = queue.Queue()
        observer = Observer()
        observer.schedule(XdfHandler(packet_queue), str(xdf_dir), recursive=True)
        observer.start()
        inference = EegInference(self.config.model_path, self.state, self.on_sample)
        try:
            while not self._stop_event.is_set():
                start = time.time()
                while True:
                    try:
                        stream_name, file_path = packet_queue.get_nowait()
                    except queue.Empty:
                        break
                    if stream_name == "eeg":
                        inference.read_eeg_packet(file_path)
                    elif stream_name == "eye":
                        inference.read_eye_packet(file_path)
                time.sleep(max(0.0, 0.5 - (time.time() - start)))
        finally:
            observer.stop()
            observer.join()

    def _wait_for_xdf_dir(self, session_dir: Path, timeout: float = 10.0) -> Path | None:
        xdf_dir = session_dir / "xdf"
        deadline = time.time() + timeout
        while time.time() < deadline and not self._stop_event.is_set():
            if xdf_dir.exists():
                return xdf_dir
            time.sleep(0.5)
        self.state.log(f"xdf directory not found in {session_dir}")
        return None


class _RootHandler(FileSystemEventHandler):
    def __init__(self, watcher: RealStreamWatcher) -> None:
        super().__init__()
        self.watcher = watcher

    def on_created(self, event) -> None:
        if not event.is_directory:
            return
        session_path = Path(event.src_path)
        keyword = self.watcher.config.session_keyword
        if keyword and keyword not in session_path.name:
            return
        self.watcher.state.log(f"New session directory: {session_path}")
        self.watcher.start_session(session_path)

