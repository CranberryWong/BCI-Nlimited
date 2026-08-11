from __future__ import annotations

from typing import Any

from .schemas import FormState, HarmonyPlan, MotifPlan, TonalPlan


class NotochordHarmonyCandidateProvider:
    """Optional Notochord adapter limited to bass/inner-voice candidates."""

    def __init__(self, melody_model: Any) -> None:
        self.melody_model = melody_model

    @property
    def available(self) -> bool:
        return bool(
            getattr(self.melody_model, "active_provider", "rule") == "notochord"
            and getattr(self.melody_model, "model", None) is not None
        )

    def propose(self, tonal: TonalPlan, motif: MotifPlan, form: FormState, rule: HarmonyPlan) -> list[int]:
        if not self.available:
            raise RuntimeError("Notochord model unavailable")
        model = self.melody_model.model
        model.reset()
        result: list[int] = []
        seconds_per_chord = motif.beats_per_bar * 60.0 / 84.0
        instrument = int(getattr(self.melody_model, "notochord_instrument", 14))
        for index, root in enumerate(rule.roots):
            choices = [pitch for pitch in range(36, 61) if pitch % 12 in {root, (root + 7) % 12}]
            candidate = model.query(
                next_inst=instrument,
                next_time=0.0 if index == 0 else seconds_per_chord,
                include_pitch=choices,
                min_vel=38,
                max_vel=78,
                pitch_temp=0.65,
                velocity_temp=0.55,
            )
            pitch = int(self._number(candidate["pitch"]))
            if pitch not in choices:
                raise RuntimeError(f"Notochord returned out-of-constraint pitch {pitch}")
            result.append(pitch)
            model.feed(instrument, pitch, 0.0, int(self._number(candidate["vel"])))
            model.feed(instrument, pitch, seconds_per_chord * 0.85, 0)
        return result

    @staticmethod
    def _number(value: Any) -> float:
        return float(value.item()) if hasattr(value, "item") else float(value)
