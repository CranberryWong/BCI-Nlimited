from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from app.music.schemas import ActiveMusicConfig, TrackConfig


SAFE_FALLBACK = {
    "global": {
        "bpm": 96,
        "root_note": "C",
        "scale": "auto",
        "quantization": "1/8",
        "swing": 0.0,
        "humanize": 0.1,
        "master_velocity": 0.8,
        "master_density": 0.6,
        "output_mode": "mock",
    },
    "emotion_profiles": {},
    "default_tracks": [],
    "music_parameter_schema": {},
}


class MusicConfigStore:
    def __init__(self, defaults_path: Path) -> None:
        self.defaults_path = defaults_path
        self._defaults_raw = self._read_file(defaults_path) or copy.deepcopy(SAFE_FALLBACK)
        self._default_config = self._normalize(self._defaults_raw)
        self.active_config = self._default_config.model_copy(deep=True)

    def api_payload(self) -> dict[str, Any]:
        payload = self.active_config.as_api()
        payload["default_schema"] = copy.deepcopy(self._defaults_raw)
        return payload

    def export_yaml(self) -> str:
        return yaml.safe_dump(self.active_config.as_api(), allow_unicode=True, sort_keys=False)

    def reset(self) -> ActiveMusicConfig:
        self.active_config = self._default_config.model_copy(deep=True)
        return self.active_config

    def replace(self, payload: dict[str, Any]) -> ActiveMusicConfig:
        self.active_config = self._normalize(payload)
        return self.active_config

    def import_text(self, text: str) -> ActiveMusicConfig:
        payload = yaml.safe_load(text)
        if not isinstance(payload, dict):
            raise ValueError("music config must be a YAML or JSON object")
        return self.replace(payload)

    def patch_track(self, track_id: str, patch: dict[str, Any]) -> TrackConfig:
        tracks = self.active_config.tracks
        for index, track in enumerate(tracks):
            if track.id == track_id:
                merged = track.model_dump()
                merged.update(patch)
                tracks[index] = TrackConfig.model_validate(merged)
                return tracks[index]
        raise KeyError(track_id)

    def reset_track(self, track_id: str) -> TrackConfig:
        default_by_id = {track.id: track for track in self._default_config.tracks}
        if track_id not in default_by_id:
            raise KeyError(track_id)
        default_track = default_by_id[track_id].model_copy(deep=True)
        for index, track in enumerate(self.active_config.tracks):
            if track.id == track_id:
                self.active_config.tracks[index] = default_track
                return default_track
        self.active_config.tracks.append(default_track)
        return default_track

    def add_track(self, track: TrackConfig) -> TrackConfig:
        if any(existing.id == track.id for existing in self.active_config.tracks):
            raise ValueError(f"track id already exists: {track.id}")
        self.active_config.tracks.append(track)
        return track

    def delete_track(self, track_id: str) -> None:
        old_count = len(self.active_config.tracks)
        self.active_config.tracks = [track for track in self.active_config.tracks if track.id != track_id]
        if len(self.active_config.tracks) == old_count:
            raise KeyError(track_id)

    @staticmethod
    def _read_file(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _default_value(value: Any) -> Any:
        return copy.deepcopy(value["default"]) if isinstance(value, dict) and "default" in value else value

    def _normalize(self, raw: dict[str, Any]) -> ActiveMusicConfig:
        global_raw = raw.get("global", SAFE_FALLBACK["global"])
        compact = {
            "global": {key: self._default_value(value) for key, value in global_raw.items()},
            "emotion_profiles": raw.get("emotion_profiles", {}),
            "default_tracks": raw.get("default_tracks") or raw.get("tracks") or [],
            "music_parameter_schema": raw.get("music_parameter_schema") or raw.get("parameter_schema") or {},
        }
        return ActiveMusicConfig.model_validate(compact)
