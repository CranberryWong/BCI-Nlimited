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

    def propose(
        self,
        tonal: TonalPlan,
        motif: MotifPlan,
        form: FormState,
        rule: HarmonyPlan,
        roles: set[str],
    ) -> dict[str, list]:
        if not self.available:
            raise RuntimeError("Notochord model unavailable")
        model = self.melody_model.model
        seconds_per_chord = motif.beats_per_bar * 60.0 / 84.0
        instrument = int(getattr(self.melody_model, "notochord_instrument", 14))
        result: dict[str, list] = {}
        if "bass" in roles:
            choices = [
                [pitch for pitch in range(36, 61) if pitch % 12 in {root, (root + 7) % 12}]
                for root in rule.roots
            ]
            result["bass"] = self._phrase(model, instrument, choices, seconds_per_chord)
        if "harmony" in roles:
            voicings: list[list[int]] = []
            for rule_voicing in rule.pad_voicings:
                pitch_classes = [pitch % 12 for pitch in rule_voicing]
                chord_choices = [
                    [pitch for pitch in range(48, 73) if pitch % 12 == pitch_class]
                    for pitch_class in pitch_classes
                ]
                voicings.append(self._phrase(model, instrument, chord_choices, 0.03))
            result["harmony"] = voicings
        if "inner_voice" in roles:
            choices = [
                [pitch for pitch in range(55, 73) if pitch % 12 in {tone % 12 for tone in voicing}]
                for voicing in rule.pad_voicings
            ]
            result["inner_voice"] = self._phrase(model, instrument, choices, seconds_per_chord)
        return result

    def _phrase(self, model: Any, instrument: int, choices_by_event: list[list[int]], spacing: float) -> list[int]:
        model.reset()
        result: list[int] = []
        for index, choices in enumerate(choices_by_event):
            candidate = model.query(
                next_inst=instrument,
                next_time=0.0 if index == 0 else spacing,
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
            velocity = int(self._number(candidate["vel"]))
            model.feed(instrument, pitch, 0.0, velocity)
            model.feed(instrument, pitch, max(0.02, spacing * 0.85), 0)
        return result

    @staticmethod
    def _number(value: Any) -> float:
        return float(value.item()) if hasattr(value, "item") else float(value)
