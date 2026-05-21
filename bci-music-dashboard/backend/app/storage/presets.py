from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import yaml


BUILTIN_PRESETS = {
    "ambient-neurofeedback": "Ambient Neurofeedback",
    "piano-emotion-melody": "Piano Emotion Melody",
    "percussive-arousal": "Percussive Arousal",
    "max-msp-osc-bridge": "Max/MSP OSC Bridge",
}


class PresetStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict[str, Any]]:
        files = [{"id": path.stem, "name": path.stem.replace("-", " ").title(), "builtin": False} for path in sorted(self.root.glob("*.yaml"))]
        builtins = [{"id": key, "name": value, "builtin": True} for key, value in BUILTIN_PRESETS.items()]
        return builtins + files

    def save(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"preset-{int(time.time())}"
        path = self.root / f"{slug}.yaml"
        path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return {"id": slug, "name": name, "builtin": False}

    def load(self, preset_id: str, default_config: dict[str, Any]) -> dict[str, Any]:
        if preset_id in BUILTIN_PRESETS:
            config = yaml.safe_load(yaml.safe_dump(default_config, allow_unicode=True))
            if preset_id == "piano-emotion-melody":
                config["default_tracks"] = [track for track in config["default_tracks"] if track["role"] == "melody"]
            elif preset_id == "percussive-arousal":
                config["default_tracks"] = [track for track in config["default_tracks"] if track["role"] in {"drum", "cymbal"}]
            elif preset_id == "max-msp-osc-bridge":
                config["global"]["output_mode"] = "osc"
                for track in config["default_tracks"]:
                    track["output_type"] = "osc"
            return config
        path = self.root / f"{preset_id}.yaml"
        if not path.exists():
            raise FileNotFoundError(path)
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("preset is not an object")
        return payload
