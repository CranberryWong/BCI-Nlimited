from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EmotionLabel = Literal["joy", "calm", "neutral", "tense", "sad"]
TrackRole = Literal["melody", "chord", "bass", "drum", "cymbal", "pad", "fx"]
OutputType = Literal["midi", "osc"]
MusicEventType = Literal["note_on", "note_off", "control", "osc"]


class EmotionState(BaseModel):
    valence_class: int = Field(ge=1, le=9)
    arousal_class: int = Field(ge=1, le=9)
    valence_prob: float = Field(ge=0.0, le=1.0)
    arousal_prob: float = Field(ge=0.0, le=1.0)
    valence_norm: float = Field(ge=0.0, le=1.0)
    arousal_norm: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    label: EmotionLabel
    timestamp: float = Field(default_factory=time.time)
    source: Literal["real_model", "simulator", "osc_input"] = "osc_input"


class TrackMapping(BaseModel):
    valence_to_pitch: float = Field(default=0.5, ge=-1.0, le=1.0)
    arousal_to_velocity: float = Field(default=0.5, ge=-1.0, le=1.0)
    arousal_to_density: float = Field(default=0.5, ge=-1.0, le=1.0)
    probability_to_randomness: float = Field(default=-0.4, ge=-1.0, le=1.0)


class TrackConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    enabled: bool = True
    compute_enabled: bool = True
    role: TrackRole
    instrument: str
    output_type: OutputType = "osc"
    target_ip: str = "127.0.0.1"
    target_port: int = Field(default=57120, ge=1, le=65535)
    midi_channel: int = Field(default=1, ge=1, le=16)
    midi_program: int | None = Field(default=None, ge=0, le=127)
    root_note: str = "auto"
    scale: str = "auto"
    pitch_range: tuple[int, int] = (48, 84)
    velocity_range: tuple[int, int] = (30, 100)
    bpm: int | Literal["auto"] = "auto"
    density: float = Field(default=0.5, ge=0.0, le=1.0)
    polyphony: int = Field(default=1, ge=1, le=8)
    delay_ms: int = Field(default=0, ge=0, le=5000)
    note_length_ms: int = Field(default=250, ge=20, le=10000)
    humanize: float = Field(default=0.1, ge=0.0, le=1.0)
    editable_params: list[str] = Field(default_factory=list)
    mapping: TrackMapping = Field(default_factory=TrackMapping)

    @field_validator("pitch_range", "velocity_range")
    @classmethod
    def validate_ranges(cls, value: tuple[int, int]) -> tuple[int, int]:
        low, high = value
        if not 0 <= low <= high <= 127:
            raise ValueError("range must stay within MIDI 0..127")
        return value

    @field_validator("bpm")
    @classmethod
    def validate_bpm(cls, value: int | str) -> int | str:
        if value != "auto" and not 30 <= int(value) <= 220:
            raise ValueError("bpm must be auto or 30..220")
        return value


class MusicEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    track_id: str
    type: MusicEventType
    pitch: int | None = Field(default=None, ge=0, le=127)
    velocity: int | None = Field(default=None, ge=0, le=127)
    duration_ms: int | None = Field(default=None, ge=0)
    channel: int | None = Field(default=None, ge=1, le=16)
    address: str | None = None
    args: list[Any] = Field(default_factory=list)


class GlobalMusicConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    bpm: int = Field(default=96, ge=30, le=220)
    root_note: str = "C"
    scale: str = "auto"
    quantization: str = "1/8"
    swing: float = Field(default=0.0, ge=0.0, le=0.7)
    humanize: float = Field(default=0.12, ge=0.0, le=1.0)
    master_velocity: float = Field(default=0.8, ge=0.0, le=1.0)
    master_density: float = Field(default=0.6, ge=0.0, le=1.0)
    output_mode: Literal["osc", "midi", "both", "mock"] = "osc"


class EmotionProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    label_zh: str
    scale: str
    bpm_range: tuple[int, int]
    pitch_range: tuple[int, int]
    velocity_range: tuple[int, int]
    density_range: tuple[float, float]
    delay_ms_range: tuple[int, int]
    chord_quality: str
    brightness: float = Field(ge=0.0, le=1.0)
    tension: float = Field(ge=0.0, le=1.0)
    editable: bool = True


class ActiveMusicConfig(BaseModel):
    global_settings: GlobalMusicConfig = Field(alias="global")
    emotion_profiles: dict[EmotionLabel, EmotionProfile]
    tracks: list[TrackConfig] = Field(alias="default_tracks")
    parameter_schema: dict[str, Any] = Field(default_factory=dict, alias="music_parameter_schema")

    model_config = ConfigDict(populate_by_name=True)

    def as_api(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
