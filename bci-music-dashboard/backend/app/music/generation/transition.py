from __future__ import annotations

from dataclasses import dataclass

from app.music.schemas import EmotionLabel


@dataclass(frozen=True)
class TransitionPlan:
    transition_type: str
    from_emotion: EmotionLabel
    to_emotion: EmotionLabel
    progress: float
    strategy: str
    preparing: bool


class EmotionTransitionPlanner:
    STRATEGIES: dict[tuple[EmotionLabel, EmotionLabel], str] = {
        ("sad", "joy"): "warmth_to_uplift",
        ("tense", "calm"): "grounding_release",
        ("calm", "joy"): "open_to_lift",
        ("neutral", "joy"): "curiosity_to_lift",
        ("joy", "calm"): "bright_settle",
    }

    def __init__(self) -> None:
        self.current: EmotionLabel = "neutral"
        self.target: EmotionLabel = "neutral"
        self.progress = 0.0

    def plan(
        self,
        current: EmotionLabel,
        candidate: EmotionLabel,
        section_phrase: int,
        is_boundary: bool,
    ) -> TransitionPlan:
        if candidate == current:
            self.current = current
            self.target = current
            self.progress = 0.0
            return TransitionPlan("continue", current, current, 0.0, "none", False)

        strategy = self.STRATEGIES.get((current, candidate), "crossfade")
        preparing = section_phrase == 0 or is_boundary
        self.current = current
        self.target = candidate
        self.progress = 0.5 if preparing else 1.0
        return TransitionPlan(
            "emotion_transition",
            current,
            candidate,
            self.progress,
            strategy,
            preparing,
        )
