from __future__ import annotations

import time

from .schemas import ContextFrame, MusicIntent


class PolicyEngine:
    """BCI-led, explainable mapping from normalized context to musical intent."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.previous: MusicIntent | None = None
        self.previous_at: float | None = None

    def resolve(self, context: ContextFrame) -> MusicIntent:
        weights = self.config.get("weights", {})
        heart = self._heart_energy(context.heart_rate)
        motion = context.motion if context.motion is not None else context.arousal
        cadence = min(1.0, (context.cadence or 0.0) / 140.0) if context.cadence is not None else motion
        expansion = context.posture_expansion if context.posture_expansion is not None else 0.5

        energy = self._mix(weights.get("energy", {}), {
            "bci_arousal": context.arousal,
            "heart_rate": heart,
            "motion": motion,
            "circadian": context.circadian_energy,
        }, fallback=context.arousal)
        pulse = self._mix(weights.get("pulse", {}), {
            "bci_arousal": context.arousal,
            "cadence": cadence,
            "heart_rate": heart,
        }, fallback=context.arousal)
        brightness = self._mix(weights.get("brightness", {}), {
            "bci_valence": context.valence,
            "daylight": context.daylight,
            "weather": context.weather_brightness,
        }, fallback=context.valence)
        spatial = self._mix(weights.get("spatial_width", {}), {
            "motion": motion,
            "posture_expansion": expansion,
            "baseline": 0.5,
        }, fallback=0.5)
        tension = self._clamp((1.0 - context.valence) * context.arousal * 0.85 + heart * 0.10 + (1.0 - (context.posture_symmetry or 0.5)) * 0.05)
        density = self._clamp(0.15 + energy * 0.55 + pulse * 0.30)
        complexity = self._clamp(0.15 + energy * 0.35 + context.bci_confidence * 0.30 + motion * 0.20)
        gesture_accent = 0.18 if context.gesture and context.gesture.lower() not in {"", "none", "idle"} else 0.0
        urgency = self._clamp(abs(context.arousal - 0.5) * 0.65 + tension * 0.35 + gesture_accent)
        freeze_below = float(self.config.get("confidence", {}).get("freeze_motif_below", 0.45))

        target = MusicIntent(
            valence=context.valence,
            energy=energy,
            tension=tension,
            density=density,
            brightness=brightness,
            pulse=pulse,
            complexity=complexity,
            register_band=self._register(context.valence, energy),
            articulation=self._articulation(energy, tension, context.gesture, context.posture_verticality),
            spatial_width=spatial,
            transition_urgency=urgency,
            confidence=context.bci_confidence,
            frozen_motif=context.bci_confidence < freeze_below or context.degraded,
        )
        result = self._smooth(target)
        self.previous = result
        self.previous_at = context.timestamp
        return result

    def _smooth(self, target: MusicIntent) -> MusicIntent:
        if self.previous is None or self.previous_at is None:
            return target
        elapsed = max(0.001, target.timestamp - self.previous_at)
        smoothing = self.config.get("smoothing", {})
        deadband = float(smoothing.get("deadband", 0.03))
        values = target.model_dump()
        for field in ("valence", "energy", "tension", "density", "brightness", "pulse", "complexity", "spatial_width", "transition_urgency"):
            old = float(getattr(self.previous, field))
            new = float(getattr(target, field))
            if abs(new - old) < deadband:
                values[field] = old
                continue
            seconds = float(smoothing.get("attack_seconds" if new > old else "release_seconds", 2.0))
            amount = min(1.0, elapsed / max(0.01, seconds))
            values[field] = old + (new - old) * amount
        return MusicIntent.model_validate(values)

    @staticmethod
    def _mix(weights: dict, values: dict[str, float], fallback: float) -> float:
        total = sum(max(0.0, float(weights.get(key, 0.0))) for key in values)
        if total <= 0:
            return fallback
        return PolicyEngine._clamp(sum(float(weights.get(key, 0.0)) * value for key, value in values.items()) / total)

    @staticmethod
    def _heart_energy(heart_rate: float | None) -> float:
        if heart_rate is None:
            return 0.5
        return PolicyEngine._clamp((heart_rate - 50.0) / 100.0)

    @staticmethod
    def _register(valence: float, energy: float) -> str:
        if energy > 0.82:
            return "wide"
        if valence > 0.7:
            return "high"
        if valence < 0.3:
            return "low"
        return "mid_high" if energy > 0.6 else "mid"

    @staticmethod
    def _articulation(energy: float, tension: float, gesture: str | None = None, verticality: float | None = None) -> str:
        if gesture and gesture.lower() not in {"", "none", "idle"}:
            return "accented"
        if tension > 0.72:
            return "accented"
        if verticality is not None and verticality > 0.75:
            return "detached"
        if energy > 0.68:
            return "detached"
        if energy < 0.28:
            return "sustained"
        if energy < 0.43:
            return "soft"
        return "balanced"

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
