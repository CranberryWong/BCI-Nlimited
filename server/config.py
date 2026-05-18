from __future__ import annotations

import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _default_root_dir() -> str:
    if platform.system() == "Windows":
        return r"C:\Users\SJTU\.leaf\record"
    return str(Path.home() / ".leaf" / "record")


@dataclass
class AppConfig:
    host: str = os.getenv("BCI_HOST", "0.0.0.0")
    port: int = int(os.getenv("BCI_PORT", "5000"))
    xdf_root_dir: str = os.getenv("XDF_ROOT_DIR", _default_root_dir())
    session_keyword: str = os.getenv("SESSION_KEYWORD", "BCI")
    model_path: str = os.getenv(
        "MODEL_PATH",
        str(Path(__file__).resolve().parents[2] / "train" / "mlp_valence_model.pkl"),
    )
    osc_target_ip: str = os.getenv("OSC_TARGET_IP", "127.0.0.1")
    osc_target_port: int = int(os.getenv("OSC_TARGET_PORT", "8000"))
    osc_address: str = os.getenv("OSC_ADDRESS", "/eeg/valence_arousal")
    midi_enabled: bool = os.getenv("MIDI_ENABLED", "0") == "1"
    midi_port_name: str = os.getenv("MIDI_PORT_NAME", "")
    midi_channel: int = int(os.getenv("MIDI_CHANNEL", "0"))
    valence_cc: int = int(os.getenv("MIDI_VALENCE_CC", "20"))
    arousal_cc: int = int(os.getenv("MIDI_AROUSAL_CC", "21"))
    confidence_cc: int = int(os.getenv("MIDI_CONFIDENCE_CC", "22"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def update(self, values: dict[str, Any]) -> None:
        editable = set(self.to_dict().keys())
        for key, value in values.items():
            if key not in editable:
                continue
            current = getattr(self, key)
            if isinstance(current, bool):
                value = bool(value)
            elif isinstance(current, int):
                value = int(value)
            setattr(self, key, value)


def load_config() -> AppConfig:
    return AppConfig()
