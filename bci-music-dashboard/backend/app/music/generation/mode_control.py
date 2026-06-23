from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.music.schemas import (
    EmotionLabel,
    EmotionState,
    EngagingStageConfig,
    MusicParams,
    SystemMode,
    SystemModesConfig,
)


DEFAULT_MAPPINGS: dict[EmotionLabel, MusicParams] = {
    "calm": MusicParams(
        tempo=68,
        density=0.25,
        velocity=0.35,
        register="mid_high",
        scale="major_pentatonic",
        mode="soft",
        instruments={"xylophone": 0.45, "pad": 0.35, "bass": 0.2},
        reverb=0.68,
        delay=0.22,
        rhythm_complexity=0.2,
        brightness=0.62,
        tension=0.06,
    ),
    "joy": MusicParams(
        tempo=116,
        density=0.82,
        velocity=0.78,
        register="high",
        scale="bright_pentatonic",
        mode="major",
        instruments={"xylophone": 0.5, "pad": 0.2, "drum": 0.2, "cymbal": 0.1},
        reverb=0.45,
        delay=0.18,
        rhythm_complexity=0.62,
        brightness=0.9,
        tension=0.12,
    ),
    "neutral": MusicParams(
        tempo=88,
        density=0.5,
        velocity=0.52,
        register="mid",
        scale="gong",
        mode="stable",
        instruments={"xylophone": 0.45, "pad": 0.25, "bass": 0.2, "drum": 0.1},
        reverb=0.32,
        delay=0.1,
        rhythm_complexity=0.35,
        brightness=0.52,
        tension=0.1,
    ),
    "sad": MusicParams(
        tempo=62,
        density=0.22,
        velocity=0.32,
        register="low",
        scale="yu",
        mode="dark_pentatonic",
        instruments={"xylophone": 0.28, "pad": 0.42, "bass": 0.3},
        reverb=0.72,
        delay=0.24,
        rhythm_complexity=0.18,
        brightness=0.28,
        tension=0.32,
    ),
    "tense": MusicParams(
        tempo=126,
        density=0.76,
        velocity=0.74,
        register="wide",
        scale="jue",
        mode="controlled_tension",
        instruments={"xylophone": 0.38, "bass": 0.22, "drum": 0.28, "cymbal": 0.12},
        reverb=0.26,
        delay=0.36,
        rhythm_complexity=0.82,
        brightness=0.48,
        tension=0.78,
    ),
}

DEFAULT_STAGES = [
    EngagingStageConfig(name="Resonance", start=0, end=40),
    EngagingStageConfig(name="Regulation", start=40, end=90),
    EngagingStageConfig(name="Activation", start=90, end=150),
    EngagingStageConfig(name="Elevation", start=150, end=220),
    EngagingStageConfig(name="Integration", start=220, end=240),
]

REGISTER_ORDER = ["low", "mid", "mid_high", "high", "wide"]


@dataclass(frozen=True)
class ModeSnapshot:
    system_mode: SystemMode
    raw_emotion: dict[str, Any] | None
    smoothed_emotion: dict[str, Any] | None
    music_params: MusicParams
    engaging_stage: str | None
    stage_elapsed_sec: float
    stage_progress: float
    target_state_progress: float


class ModeController:
    def __init__(self, config: SystemModesConfig, mode: SystemMode = "ENGAGING") -> None:
        self.config = self._with_defaults(config)
        self.mode: SystemMode = mode
        self.raw_emotion: EmotionState | None = None
        self.smoothed_label: EmotionLabel = "neutral"
        self.smoothed_valence = 0.5
        self.smoothed_arousal = 0.5
        self.smoothed_confidence = 0.0
        self.music_params = self.config.MIRROR.emotion_mappings["neutral"]
        self.started_at: float | None = None
        self.initial_emotion: EmotionLabel = "neutral"
        self.current_stage = "Resonance"

    @staticmethod
    def _with_defaults(config: SystemModesConfig) -> SystemModesConfig:
        mirror = config.MIRROR.model_copy(deep=True)
        merged = dict(DEFAULT_MAPPINGS)
        merged.update(mirror.emotion_mappings)
        mirror.emotion_mappings = merged
        engaging = config.ENGAGING.model_copy(deep=True)
        if not engaging.stages:
            engaging.stages = list(DEFAULT_STAGES)
        return SystemModesConfig(MIRROR=mirror, ENGAGING=engaging)

    def configure(self, config: SystemModesConfig) -> None:
        old_mode = self.mode
        self.config = self._with_defaults(config)
        self.mode = old_mode
        self.music_params = self._current_target_params()

    def set_mode(self, mode: SystemMode) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        self.started_at = time.monotonic()
        self.initial_emotion = self.smoothed_label
        self.music_params = self._current_target_params()

    def start(self) -> None:
        self.started_at = time.monotonic()
        self.initial_emotion = self.smoothed_label
        self.music_params = self._current_target_params()

    def update_emotion(self, emotion: EmotionState) -> None:
        self.raw_emotion = emotion
        smoothing = (
            self.config.MIRROR.smoothing
            if self.mode == "MIRROR"
            else self.config.ENGAGING.smoothing
        )
        alpha = max(0.0, min(1.0, smoothing))
        self.smoothed_valence = self._lerp(self.smoothed_valence, emotion.valence_norm, alpha)
        self.smoothed_arousal = self._lerp(self.smoothed_arousal, emotion.arousal_norm, alpha)
        self.smoothed_confidence = self._lerp(self.smoothed_confidence, emotion.confidence, alpha)
        if emotion.confidence >= max(0.45, self.smoothed_confidence - 0.05):
            self.smoothed_label = emotion.label
        target = self._current_target_params()
        self.music_params = self._blend_params(self.music_params, target, alpha)

    def target_bpm_for(self, label: EmotionLabel, fallback: int) -> int:
        params = self._current_target_params()
        if self.mode == "MIRROR":
            return params.tempo
        return round(self._lerp(fallback, params.tempo, 0.65))

    def composition_label(self, fallback: EmotionLabel) -> EmotionLabel:
        if self.mode == "MIRROR":
            return self.smoothed_label
        stage, _elapsed, _progress = self._stage_state()
        if stage == "Resonance":
            return fallback
        if stage == "Regulation":
            return "calm" if fallback in {"tense", "sad"} else "neutral"
        if stage in {"Activation", "Elevation"}:
            return "joy"
        return "calm" if fallback in {"calm", "joy"} else "neutral"

    def expression_controls(self) -> dict[str, tuple[str, float]]:
        params = self.music_params
        return {
            "melody": ("expression", self._clamp(0.25 + params.velocity * 0.45 + params.density * 0.25)),
            "pad": ("brightness", self._clamp(params.brightness)),
            "bass": ("intensity", self._clamp(0.25 + params.tension * 0.25 + params.density * 0.35)),
            "drum": ("intensity", self._clamp(params.density * 0.75 + params.rhythm_complexity * 0.25)),
            "cymbal": ("brightness", self._clamp(params.brightness * 0.7 + params.tension * 0.2)),
        }

    def snapshot(self) -> ModeSnapshot:
        stage, elapsed, progress = self._stage_state()
        return ModeSnapshot(
            system_mode=self.mode,
            raw_emotion=self._emotion_dump(self.raw_emotion),
            smoothed_emotion={
                "label": self.smoothed_label,
                "valence_norm": round(self.smoothed_valence, 3),
                "arousal_norm": round(self.smoothed_arousal, 3),
                "confidence": round(self.smoothed_confidence, 3),
            },
            music_params=self.music_params,
            engaging_stage=stage if self.mode == "ENGAGING" else None,
            stage_elapsed_sec=round(elapsed, 1),
            stage_progress=round(progress, 3),
            target_state_progress=round(self._target_progress(), 3),
        )

    def status(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "system_mode": snapshot.system_mode,
            "raw_emotion": snapshot.raw_emotion,
            "smoothed_emotion": snapshot.smoothed_emotion,
            "music_params": snapshot.music_params.model_dump(),
            "engaging_stage": snapshot.engaging_stage,
            "stage_elapsed_sec": snapshot.stage_elapsed_sec,
            "stage_progress": snapshot.stage_progress,
            "target_state_progress": snapshot.target_state_progress,
        }

    def _current_target_params(self) -> MusicParams:
        if self.mode == "MIRROR":
            return self._mirror_target()
        return self._engaging_target()

    def _mirror_target(self) -> MusicParams:
        mapping = self.config.MIRROR.emotion_mappings
        primary = mapping.get(self.smoothed_label, mapping["neutral"])
        neutral = mapping["neutral"]
        confidence = self._clamp(self.smoothed_confidence)
        return self._blend_params(neutral, primary, 0.35 + confidence * 0.65)

    def _engaging_target(self) -> MusicParams:
        stage, _elapsed, progress = self._stage_state()
        current = self.config.MIRROR.emotion_mappings.get(self.smoothed_label, DEFAULT_MAPPINGS["neutral"])
        target = DEFAULT_MAPPINGS["joy"].model_copy(update={
            "tempo": 104,
            "density": 0.68,
            "velocity": 0.68,
            "register": "mid_high",
            "rhythm_complexity": 0.55,
            "brightness": 0.82,
            "tension": 0.18,
            "reverb": 0.48,
            "delay": 0.16,
        })
        if stage == "Resonance":
            return self._blend_params(current, target, 0.15 * progress)
        if stage == "Regulation":
            regulated = self._blend_params(current, DEFAULT_MAPPINGS["neutral"], 0.55)
            regulated = regulated.model_copy(update={
                "rhythm_complexity": min(regulated.rhythm_complexity, 0.38),
                "tension": min(regulated.tension, 0.24),
            })
            return self._blend_params(regulated, target, 0.15 + 0.2 * progress)
        if stage == "Activation":
            return self._blend_params(DEFAULT_MAPPINGS["neutral"], target, 0.35 + 0.45 * progress)
        if stage == "Elevation":
            elevated = target.model_copy(update={
                "tempo": 112,
                "density": 0.84,
                "velocity": 0.78,
                "register": "high",
                "brightness": 0.95,
                "rhythm_complexity": 0.66,
                "tension": 0.16,
            })
            return self._feedback_adjust(elevated)
        integration = target.model_copy(update={
            "tempo": 92,
            "density": 0.48,
            "velocity": 0.58,
            "register": "mid_high",
            "brightness": 0.78,
            "rhythm_complexity": 0.34,
            "reverb": 0.58,
        })
        return self._feedback_adjust(integration)

    def _feedback_adjust(self, params: MusicParams) -> MusicParams:
        data: dict[str, Any] = {}
        if self.smoothed_arousal > 0.78:
            data["tempo"] = max(60, params.tempo - 8)
            data["density"] = max(0.25, params.density - 0.16)
            data["rhythm_complexity"] = max(0.2, params.rhythm_complexity - 0.18)
            data["tension"] = max(0.08, params.tension - 0.08)
        elif self.smoothed_arousal < 0.34:
            data["tempo"] = min(130, params.tempo + 6)
            data["density"] = min(0.9, params.density + 0.12)
            data["brightness"] = min(1.0, params.brightness + 0.08)
        if self.smoothed_valence < 0.38:
            data["brightness"] = min(1.0, data.get("brightness", params.brightness) + 0.1)
            data["velocity"] = max(0.35, params.velocity - 0.04)
            data["tension"] = min(data.get("tension", params.tension), 0.24)
        if params.tension > 0.55:
            data["tension"] = 0.35
            data["rhythm_complexity"] = min(data.get("rhythm_complexity", params.rhythm_complexity), 0.45)
        return params.model_copy(update=data)

    def _stage_state(self) -> tuple[str, float, float]:
        if self.started_at is None:
            return ("Resonance", 0.0, 0.0)
        elapsed = max(0.0, time.monotonic() - self.started_at)
        stages = self.config.ENGAGING.stages or DEFAULT_STAGES
        current = stages[-1]
        for stage in stages:
            if stage.start <= elapsed < stage.end:
                current = stage
                break
        stage_elapsed = max(0.0, elapsed - current.start)
        duration = max(1.0, current.end - current.start)
        progress = self._clamp(stage_elapsed / duration)
        return (current.name, stage_elapsed, progress)

    def _target_progress(self) -> float:
        target = self.config.ENGAGING.target_state
        valence_score = 1.0 - abs(target.valence - self.smoothed_valence)
        arousal_score = 1.0 - abs(target.arousal - self.smoothed_arousal)
        tension_score = 1.0 - abs(target.tension - self.music_params.tension)
        return self._clamp((valence_score + arousal_score + tension_score) / 3)

    @staticmethod
    def _blend_params(a: MusicParams, b: MusicParams, amount: float) -> MusicParams:
        t = max(0.0, min(1.0, amount))
        register_index = round(ModeController._lerp(
            REGISTER_ORDER.index(a.register),
            REGISTER_ORDER.index(b.register),
            t,
        ))
        instruments = {
            key: round(ModeController._lerp(a.instruments.get(key, 0.0), b.instruments.get(key, 0.0), t), 3)
            for key in set(a.instruments) | set(b.instruments)
        }
        return MusicParams(
            tempo=round(ModeController._lerp(a.tempo, b.tempo, t)),
            density=ModeController._clamp(ModeController._lerp(a.density, b.density, t)),
            velocity=ModeController._clamp(ModeController._lerp(a.velocity, b.velocity, t)),
            register=REGISTER_ORDER[register_index],
            scale=b.scale if t >= 0.5 else a.scale,
            mode=b.mode if t >= 0.5 else a.mode,
            instruments=instruments,
            reverb=ModeController._clamp(ModeController._lerp(a.reverb, b.reverb, t)),
            delay=ModeController._clamp(ModeController._lerp(a.delay, b.delay, t)),
            rhythm_complexity=ModeController._clamp(ModeController._lerp(a.rhythm_complexity, b.rhythm_complexity, t)),
            brightness=ModeController._clamp(ModeController._lerp(a.brightness, b.brightness, t)),
            tension=ModeController._clamp(ModeController._lerp(a.tension, b.tension, t)),
        )

    @staticmethod
    def _emotion_dump(emotion: EmotionState | None) -> dict[str, Any] | None:
        if emotion is None:
            return None
        return {
            "label": emotion.label,
            "valence_norm": round(emotion.valence_norm, 3),
            "arousal_norm": round(emotion.arousal_norm, 3),
            "confidence": round(emotion.confidence, 3),
            "source": emotion.source,
            "timestamp": emotion.timestamp,
        }

    @staticmethod
    def _lerp(a: float, b: float, amount: float) -> float:
        return a + (b - a) * amount

    @staticmethod
    def _clamp(value: float) -> float:
        return round(max(0.0, min(1.0, value)), 3)
