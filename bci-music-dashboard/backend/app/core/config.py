from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", PROJECT_DIR.parent / ".env"),
        extra="ignore",
    )

    app_name: str = "BCI Music Dashboard"
    bci_input_osc_ip: str = "0.0.0.0"
    bci_input_osc_port: int = 8000
    default_output_osc_ip: str = "127.0.0.1"
    default_output_osc_port: int = 57120
    xdf_root_dir: str = ""
    model_path: str = "models/mlp_valence_model.pkl"
    session_keyword: str = "BCI"
    frontend_origin: str = "http://localhost:5173"
    music_model_provider: str = "auto"
    music_model_path: str = "models/music/latest.pt"
    music_model_config_path: str = "models/music/model_config.json"
    notochord_checkpoint: str = "~/Library/Application Support/Notochord/notochord-latest.ckpt"
    notochord_device: str = "cpu"
    notochord_instrument: int = 14
    music_library_path: str = "music_library"

    @property
    def resolved_model_path(self) -> Path:
        candidate = Path(self.model_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return (PROJECT_DIR / candidate).resolve()

    @property
    def resolved_xdf_root_dir(self) -> Path | None:
        return Path(self.xdf_root_dir).expanduser() if self.xdf_root_dir else None

    @property
    def resolved_music_model_path(self) -> Path:
        candidate = Path(self.music_model_path).expanduser()
        return candidate if candidate.is_absolute() else (PROJECT_DIR / candidate).resolve()

    @property
    def resolved_music_model_config_path(self) -> Path:
        candidate = Path(self.music_model_config_path).expanduser()
        return candidate if candidate.is_absolute() else (PROJECT_DIR / candidate).resolve()

    @property
    def resolved_notochord_checkpoint(self) -> Path:
        candidate = Path(self.notochord_checkpoint).expanduser()
        return candidate if candidate.is_absolute() else (PROJECT_DIR / candidate).resolve()

    @property
    def music_defaults_path(self) -> Path:
        return BACKEND_DIR / "app" / "config" / "music_defaults.yaml"

    @property
    def resolved_music_library_path(self) -> Path:
        candidate = Path(self.music_library_path).expanduser()
        return candidate if candidate.is_absolute() else (PROJECT_DIR / candidate).resolve()

    @property
    def preset_dir(self) -> Path:
        return BACKEND_DIR / "data" / "presets"

    @property
    def session_dir(self) -> Path:
        return BACKEND_DIR / "data" / "sessions"


@lru_cache
def get_settings() -> Settings:
    return Settings()
