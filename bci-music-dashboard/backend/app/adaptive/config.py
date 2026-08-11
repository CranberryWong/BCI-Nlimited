from __future__ import annotations

import copy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


MODULES = (
    "inputs", "policy", "form", "tonal", "motif", "melody",
    "harmony", "orchestration", "outputs",
)


class AdaptiveConfigStore:
    """Validated-by-shape modular configuration with performance locking."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._active = {name: self._load(name) for name in MODULES}
        self._validate_all(self._active)
        self._locked_snapshot: dict[str, Any] | None = None

    @property
    def locked(self) -> bool:
        return self._locked_snapshot is not None

    def all(self) -> dict[str, Any]:
        source = self._locked_snapshot if self.locked else self._active
        return copy.deepcopy(source)

    def get(self, module: str) -> dict[str, Any]:
        self._require_module(module)
        source = self._locked_snapshot if self.locked else self._active
        return copy.deepcopy(source[module])

    def replace(self, module: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_module(module)
        if self.locked:
            raise RuntimeError("performance configuration is locked until the session stops")
        if not isinstance(payload, dict):
            raise ValueError("configuration module must be an object")
        candidate = copy.deepcopy(self._active)
        candidate[module] = copy.deepcopy(payload)
        self._validate_all(candidate)
        self._active[module] = candidate[module]
        self._persist(module, candidate[module])
        return self.get(module)

    def reset(self, module: str) -> dict[str, Any]:
        self._require_module(module)
        if self.locked:
            raise RuntimeError("performance configuration is locked until the session stops")
        self._active[module] = self._load(module)
        return self.get(module)

    def lock(self) -> dict[str, Any]:
        self._locked_snapshot = copy.deepcopy(self._active)
        return self.all()

    def unlock(self) -> None:
        self._locked_snapshot = None

    def export_yaml(self) -> str:
        return yaml.safe_dump(self.all(), allow_unicode=True, sort_keys=False)

    def merge_legacy(self, legacy: dict[str, Any]) -> list[str]:
        if self.locked:
            raise RuntimeError("performance configuration is locked until the session stops")
        from .legacy import merge_legacy_music_config

        candidate, changes = merge_legacy_music_config(self._active, legacy)
        self._validate_all(candidate)
        self._active = candidate
        return changes

    def _load(self, module: str) -> dict[str, Any]:
        path = self.root / f"{module}.yaml"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError(f"{path.name} must contain a YAML object")
        return payload

    def _persist(self, module: str, payload: dict[str, Any]) -> None:
        path = self.root / f"{module}.yaml"
        temporary = path.with_suffix(".yaml.tmp")
        temporary.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _validate_all(config: dict[str, dict[str, Any]]) -> None:
        missing = [name for name in MODULES if not isinstance(config.get(name), dict)]
        if missing:
            raise ValueError(f"missing configuration modules: {', '.join(missing)}")

        inputs = config["inputs"]
        if inputs.get("strategy") != "adaptive_performance":
            raise ValueError("inputs.strategy must be adaptive_performance")
        weather = inputs.get("weather", {})
        if weather.get("enabled") and (weather.get("latitude") is None or weather.get("longitude") is None):
            raise ValueError("enabled weather requires explicit latitude and longitude")
        if float(weather.get("timeout_seconds", 1.5)) > 1.5:
            raise ValueError("weather timeout_seconds must not exceed 1.5")

        weights = config["policy"].get("weights", {})
        for group, bci_key in (("energy", "bci_arousal"), ("pulse", "bci_arousal"), ("brightness", "bci_valence")):
            values = weights.get(group, {})
            primary = float(values.get(bci_key, 0.0))
            auxiliary = sum(max(0.0, float(value)) for key, value in values.items() if key != bci_key)
            if primary <= 0 or primary < auxiliary:
                raise ValueError(f"policy.weights.{group} must remain BCI-led")

        form = config["form"]
        sections = form.get("sections", [])
        if not sections or int(form.get("minimum_phrases_per_section", 0)) < 2:
            raise ValueError("form requires sections and at least two phrases per section")
        ids = [str(section.get("id", "")) for section in sections]
        if not all(ids) or len(ids) != len(set(ids)):
            raise ValueError("form section ids must be non-empty and unique")
        unknown_targets = {
            target for targets in form.get("transitions", {}).values() for target in targets if target not in ids
        }
        if unknown_targets:
            raise ValueError(f"unknown form transition targets: {sorted(unknown_targets)}")

        tonal = config["tonal"]
        low, high = tonal.get("melody_range", [48, 84])
        if not (0 <= int(low) < int(high) <= 127):
            raise ValueError("tonal.melody_range must be an ascending MIDI range")
        for name in (tonal.get("positive_scale"), tonal.get("negative_scale"), tonal.get("neutral_scale")):
            if name not in tonal.get("scales", {}):
                raise ValueError(f"unknown tonal scale: {name}")

        if int(config["motif"].get("beats_per_bar", 4)) != int(form.get("beats_per_bar", 4)):
            raise ValueError("motif and form beats_per_bar must match")

        worker_url = str(config["melody"].get("worker_url", ""))
        parsed = urlparse(worker_url)
        if parsed.scheme not in {"ws", "wss"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("melody.worker_url must be a localhost WebSocket URL")
        if float(config["melody"].get("frame_hz", 25)) != 25:
            raise ValueError("MRT2 conditioning frame_hz must be 25")

        if int(config["harmony"].get("counterpoint", {}).get("maximum_voices", 2)) > 2:
            raise ValueError("v1 counterpoint supports at most two voices")

        outputs = config["outputs"]
        if int(outputs.get("audio", {}).get("sample_rate", 48_000)) != 48_000:
            raise ValueError("MRT2 audio output sample_rate must be 48000")
        for role, channel in outputs.get("midi", {}).get("channels", {}).items():
            if not 1 <= int(channel) <= 16:
                raise ValueError(f"invalid MIDI channel for {role}: {channel}")
        for target in outputs.get("osc", {}).get("targets", []):
            if not target.get("id") or not target.get("host") or not 1 <= int(target.get("port", 0)) <= 65535:
                raise ValueError("every OSC target requires id, host, and a valid port")

    @staticmethod
    def _require_module(module: str) -> None:
        if module not in MODULES:
            raise KeyError(module)
