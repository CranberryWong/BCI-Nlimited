from __future__ import annotations

import math


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def probabilities_to_emotion(prob0: float, prob1: float) -> tuple[int, int]:
    pred = 0 if prob0 >= prob1 else 1
    conf = max(prob0, prob1)
    if conf < 0.6:
        delta = (prob0 - prob1) * 2.0
        valence = clip(5.0 + delta, 4, 6)
        arousal = clip(1.0 + (conf - 0.5) / 0.1 * 3.0, 1, 4)
    else:
        base = (conf - 0.6) / 0.4
        curve = math.log1p(base * 4) / math.log1p(4)
        scale = (conf - 0.6) / 0.4
        if pred == 0:
            valence = 7 + curve * 1.8
            arousal = 6 + scale * 2.5
        else:
            valence = 3 - curve * 1.8
            arousal = 5 + scale * 2.5
        valence = clip(valence, 1, 9)
        arousal = clip(arousal, 1, 9)
    return int(round(valence)), int(round(arousal))

