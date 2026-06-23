from __future__ import annotations

from collections import deque
import time

from app.bci.emotion_mapper import EmotionMapper
from app.music.schemas import EmotionLabel, EmotionState


class EmotionWindowAggregator:
    def __init__(
        self,
        window_seconds: float = 16.0,
        minimum_samples: int = 4,
        clock=time.time,
    ) -> None:
        self.window_seconds = window_seconds
        self.minimum_samples = minimum_samples
        self.clock = clock
        self.samples: deque[EmotionState] = deque()
        self.current_label: EmotionLabel = "neutral"
        self.pending_label: EmotionLabel | None = None
        self.pending_count = 0
        self.stale_windows = 0
        self.mapper = EmotionMapper()

    def add(self, emotion: EmotionState) -> None:
        self.samples.append(emotion)
        self._prune(emotion.timestamp)
        self.stale_windows = 0

    def sample_count(self) -> int:
        self._prune(self.clock())
        return len(self.samples)

    def aggregate(self, now: float | None = None) -> EmotionState:
        timestamp = self.clock() if now is None else now
        self._prune(timestamp)
        if len(self.samples) < self.minimum_samples:
            if not self.samples:
                self.stale_windows += 1
                label: EmotionLabel = self.current_label if self.stale_windows == 1 else "neutral"
            else:
                label = "neutral"
            return self._state_for_label(label, timestamp)

        total_weight = sum(max(0.05, item.confidence) for item in self.samples)
        valence = sum(item.valence_norm * max(0.05, item.confidence) for item in self.samples) / total_weight
        arousal = sum(item.arousal_norm * max(0.05, item.confidence) for item in self.samples) / total_weight
        confidence = sum(item.confidence for item in self.samples) / len(self.samples)
        candidate = self.mapper._quadrant_label(valence, arousal)
        self._apply_hysteresis(candidate, confidence, valence, arousal)
        return EmotionState(
            valence_class=round(valence * 8) + 1,
            arousal_class=round(arousal * 8) + 1,
            valence_prob=confidence,
            arousal_prob=confidence,
            valence_norm=valence,
            arousal_norm=arousal,
            confidence=confidence,
            label=self.current_label,
            timestamp=timestamp,
            source=self.samples[-1].source,
        )

    def _apply_hysteresis(
        self,
        candidate: EmotionLabel,
        confidence: float,
        valence: float,
        arousal: float,
    ) -> None:
        if candidate == self.current_label:
            self.pending_label = None
            self.pending_count = 0
            return
        current_positive = self.current_label in {"joy", "calm"}
        candidate_positive = candidate in {"joy", "calm"}
        large_crossing = current_positive != candidate_positive and abs(valence - 0.5) >= 0.28
        large_arousal_crossing = (
            (self.current_label in {"joy", "tense"}) != (candidate in {"joy", "tense"})
            and abs(arousal - 0.5) >= 0.28
        )
        if confidence >= 0.82 and (large_crossing or large_arousal_crossing):
            self.current_label = candidate
            self.pending_label = None
            self.pending_count = 0
            return
        if candidate == self.pending_label:
            self.pending_count += 1
        else:
            self.pending_label = candidate
            self.pending_count = 1
        if self.pending_count >= 2:
            self.current_label = candidate
            self.pending_label = None
            self.pending_count = 0

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()

    def _state_for_label(self, label: EmotionLabel, timestamp: float) -> EmotionState:
        centers = {
            "joy": (0.75, 0.75),
            "calm": (0.75, 0.25),
            "neutral": (0.5, 0.5),
            "tense": (0.25, 0.75),
            "sad": (0.25, 0.25),
        }
        valence, arousal = centers[label]
        return EmotionState(
            valence_class=round(valence * 8) + 1,
            arousal_class=round(arousal * 8) + 1,
            valence_prob=0.0,
            arousal_prob=0.0,
            valence_norm=valence,
            arousal_norm=arousal,
            confidence=0.0,
            label=label,
            timestamp=timestamp,
            source="simulator",
        )
