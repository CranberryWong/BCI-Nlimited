from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pyxdf


PayloadCallback = Callable[[int, int, float, float], None]


class ModelRunner:
    window_size = 300
    max_packets_per_window = 6
    expected_channels = 19
    min_pred_interval = 1.0
    excluded_labels = {"A1", "A2", "X3", "X2", "X1", "TRG"}

    def __init__(self, model_path: Path, on_payload: PayloadCallback) -> None:
        self.model_path = model_path
        self.on_payload = on_payload
        self.model = None
        self.eeg_buffer: list[np.ndarray] = []
        self.last_pred_time = -1e9

    @property
    def available(self) -> bool:
        return self.model_path.exists()

    def load(self) -> None:
        if not self.available:
            raise FileNotFoundError(f"emotion model missing at {self.model_path}")
        self.model = joblib.load(self.model_path)

    def reset(self) -> None:
        self.eeg_buffer.clear()
        self.last_pred_time = -1e9

    def process_xdf(self, file_path: Path) -> None:
        if self.model is None:
            return
        try:
            streams, _header = pyxdf.load_xdf(str(file_path), verbose=False)
        except Exception:
            return
        if not streams:
            return
        eeg_segment = np.asarray(streams[0].get("time_series", []))
        if eeg_segment.ndim != 2 or eeg_segment.size == 0:
            return
        eeg_segment = self._filter_channels(eeg_segment, streams[0])
        if eeg_segment.shape[1] > self.expected_channels:
            eeg_segment = eeg_segment[:, : self.expected_channels]
        if eeg_segment.shape[1] < self.expected_channels:
            return
        self.eeg_buffer.append(eeg_segment)
        self.eeg_buffer = self.eeg_buffer[-self.max_packets_per_window * 2 :]
        recent = self.eeg_buffer[-self.max_packets_per_window :]
        if sum(segment.shape[0] for segment in recent) < self.window_size:
            return
        now = time.monotonic()
        if now - self.last_pred_time < self.min_pred_interval:
            return
        concat = np.concatenate(recent, axis=0)[-self.window_size :, :]
        normalized = (concat - concat.mean(axis=0, keepdims=True)) / (concat.std(axis=0, keepdims=True) + 1e-6)
        probabilities = self.model.predict_proba(normalized.reshape(1, -1))[0]
        prob0, prob1 = float(probabilities[0]), float(probabilities[1])
        valence, arousal = self._probabilities_to_axes(prob0, prob1)
        self.on_payload(valence, arousal, prob0, prob1)
        self.last_pred_time = now
        self.eeg_buffer.clear()

    def _filter_channels(self, segment: np.ndarray, stream: dict) -> np.ndarray:
        try:
            channels = stream["info"]["desc"][0]["channels"][0]["channel"]
            labels = [channel["label"][0] for channel in channels]
            return segment[:, np.array([label not in self.excluded_labels for label in labels], dtype=bool)]
        except Exception:
            return segment

    @staticmethod
    def _probabilities_to_axes(prob0: float, prob1: float) -> tuple[int, int]:
        confidence = max(prob0, prob1)
        if confidence < 0.6:
            valence = np.clip(5 + (prob0 - prob1) * 2, 4, 6)
            arousal = np.clip(1 + (confidence - 0.5) / 0.1 * 3, 1, 4)
        else:
            base = (confidence - 0.6) / 0.4
            curve = np.log1p(base * 4) / np.log1p(4)
            scale = (confidence - 0.6) / 0.4
            if prob0 >= prob1:
                valence, arousal = 7 + curve * 1.8, 6 + scale * 2.5
            else:
                valence, arousal = 3 - curve * 1.8, 5 + scale * 2.5
        return int(round(float(np.clip(valence, 1, 9)))), int(round(float(np.clip(arousal, 1, 9))))
