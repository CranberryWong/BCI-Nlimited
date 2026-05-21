from __future__ import annotations

import time
from typing import Mapping

from app.music.schemas import EmotionLabel, EmotionState


class EmotionMapper:
    def __init__(self, direct_mapping: Mapping[str, EmotionLabel] | None = None) -> None:
        self.direct_mapping = dict(direct_mapping or {})

    def from_tuple(
        self,
        valence: int | float,
        arousal: int | float,
        prob0: float,
        prob1: float,
        source: str = "osc_input",
    ) -> EmotionState:
        valence_class = max(1, min(9, int(round(float(valence)))))
        arousal_class = max(1, min(9, int(round(float(arousal)))))
        valence_norm = (valence_class - 1) / 8
        arousal_norm = (arousal_class - 1) / 8
        confidence = max(0.0, min(1.0, max(float(prob0), float(prob1))))
        direct_key = f"{valence_class}:{arousal_class}"
        label = self.direct_mapping.get(direct_key) or self._quadrant_label(valence_norm, arousal_norm)
        return EmotionState(
            valence_class=valence_class,
            arousal_class=arousal_class,
            valence_prob=max(0.0, min(1.0, float(prob0))),
            arousal_prob=max(0.0, min(1.0, float(prob1))),
            valence_norm=valence_norm,
            arousal_norm=arousal_norm,
            confidence=confidence,
            label=label,
            timestamp=time.time(),
            source=source,
        )

    @staticmethod
    def _quadrant_label(valence: float, arousal: float) -> EmotionLabel:
        if 0.38 <= valence <= 0.62 and 0.38 <= arousal <= 0.62:
            return "neutral"
        if valence >= 0.5 and arousal >= 0.5:
            return "joy"
        if valence >= 0.5:
            return "calm"
        if arousal >= 0.5:
            return "tense"
        return "sad"
