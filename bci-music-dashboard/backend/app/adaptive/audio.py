from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .schemas import FormState, OrchestrationPlan


@dataclass(frozen=True)
class AudioLayerPlan:
    enabled: bool
    model_gain: float
    stem_path: str | None
    stem_gain: float
    crossfade_seconds: float
    output_device: str | int | None
    sample_rate: int

    def model_dump(self) -> dict:
        return asdict(self)


class AudioLayerEngine:
    """Resolve optional MRT2 monitoring and curated stems on one safe bus."""

    def __init__(self, melody: dict, orchestration: dict, outputs: dict, stems_root: Path | None) -> None:
        self.melody = melody
        self.orchestration = orchestration
        self.outputs = outputs
        self.stems_root = stems_root

    def plan(self, form: FormState, orchestration: OrchestrationPlan) -> AudioLayerPlan:
        audio = self.outputs.get("audio", {})
        model_audio = self.melody.get("audio", {})
        stems = self.orchestration.get("stems", {})
        enabled = bool(audio.get("enabled", True))
        master = self._gain(audio.get("master_gain", 0.65)) if enabled else 0.0
        model_gain = self._gain(model_audio.get("gain", 0.2)) * master if model_audio.get("enabled", True) else 0.0
        stem_path = self._select_stem(form.section_index) if enabled and stems.get("enabled", True) else None
        stem_gain = orchestration.stem_gain * master if stem_path else 0.0
        return AudioLayerPlan(
            enabled=enabled and (model_gain > 0 or stem_gain > 0),
            model_gain=model_gain,
            stem_path=stem_path,
            stem_gain=stem_gain,
            crossfade_seconds=max(0.01, float(stems.get("crossfade_seconds", 4))),
            output_device=audio.get("output_device"),
            sample_rate=int(audio.get("sample_rate", 48_000)),
        )

    def _select_stem(self, section_index: int) -> str | None:
        if self.stems_root is None or not self.stems_root.exists():
            return None
        candidates = sorted(
            path for path in self.stems_root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".wav", ".aif", ".aiff", ".flac"}
        )
        return str(candidates[section_index % len(candidates)].resolve()) if candidates else None

    @staticmethod
    def _gain(value) -> float:
        return max(0.0, min(1.0, float(value)))
