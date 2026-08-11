from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


InputKind = Literal["bci", "time", "weather", "heart_rate", "motion", "light", "posture", "manual"]
InputHealth = Literal["healthy", "stale", "missing", "circuit_open", "disabled", "error"]
FormRole = Literal["intro", "identity", "contrast", "development", "climax", "return", "coda"]
EventType = Literal["note_on", "note_off", "control", "transport", "state", "harmony", "section", "health"]


class InputSample(BaseModel):
    source_id: str
    kind: InputKind
    timestamp: float = Field(default_factory=time.time)
    sequence: int = Field(default=0, ge=0)
    quality: float = Field(default=1.0, ge=0.0, le=1.0)
    values: dict[str, Any] = Field(default_factory=dict)


class AdapterStatus(BaseModel):
    source_id: str
    kind: InputKind
    health: InputHealth = "missing"
    last_sample_at: float | None = None
    age_seconds: float | None = None
    quality: float = Field(default=0.0, ge=0.0, le=1.0)
    failure_count: int = 0
    detail: str = ""


class ContextFrame(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    valence: float = Field(default=0.5, ge=0.0, le=1.0)
    arousal: float = Field(default=0.5, ge=0.0, le=1.0)
    bci_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bci_age_seconds: float | None = None
    heart_rate: float | None = Field(default=None, ge=20.0, le=240.0)
    motion: float | None = Field(default=None, ge=0.0, le=1.0)
    cadence: float | None = Field(default=None, ge=0.0)
    ambient_light: float | None = Field(default=None, ge=0.0)
    daylight: float = Field(default=0.5, ge=0.0, le=1.0)
    circadian_energy: float = Field(default=0.5, ge=0.0, le=1.0)
    weather_brightness: float = Field(default=0.5, ge=0.0, le=1.0)
    precipitation: float = Field(default=0.0, ge=0.0)
    wind: float = Field(default=0.0, ge=0.0)
    posture_expansion: float | None = Field(default=None, ge=0.0, le=1.0)
    posture_symmetry: float | None = Field(default=None, ge=0.0, le=1.0)
    posture_verticality: float | None = Field(default=None, ge=0.0, le=1.0)
    gesture: str | None = None
    degraded: bool = False
    sources: dict[str, AdapterStatus] = Field(default_factory=dict)


class MusicIntent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    valence: float = Field(ge=0.0, le=1.0)
    energy: float = Field(ge=0.0, le=1.0)
    tension: float = Field(ge=0.0, le=1.0)
    density: float = Field(ge=0.0, le=1.0)
    brightness: float = Field(ge=0.0, le=1.0)
    pulse: float = Field(ge=0.0, le=1.0)
    complexity: float = Field(ge=0.0, le=1.0)
    register_band: Literal["low", "mid", "mid_high", "high", "wide"] = "mid"
    articulation: Literal["sustained", "soft", "balanced", "detached", "accented"] = "balanced"
    spatial_width: float = Field(ge=0.0, le=1.0)
    transition_urgency: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    frozen_motif: bool = False


class TonalPlan(BaseModel):
    root_note: str = "C"
    scale: str = "gong"
    pitch_classes: list[int] = Field(default_factory=lambda: [0, 2, 4, 7, 9])
    melody_range: tuple[int, int] = (48, 84)
    strong_beat_degrees: list[int] = Field(default_factory=lambda: [0, 2, 4])


class FormState(BaseModel):
    section_id: str = "intro"
    role: FormRole = "intro"
    section_index: int = 0
    phrase_in_section: int = 0
    phrase_index: int = 0
    section_count: int = 7
    emotion_changes_used: int = 0
    emotion_change_budget: int = 3
    is_final: bool = False


class MotifNote(BaseModel):
    beat: float = Field(ge=0.0)
    duration_beats: float = Field(gt=0.0)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127)
    anchor: bool = False
    mutable: bool = True
    accent: float = Field(default=0.5, ge=0.0, le=1.0)


class MotifPlan(BaseModel):
    id: str
    bars: int = Field(default=2, ge=1, le=4)
    beats_per_bar: int = Field(default=4, ge=1, le=12)
    contour: Literal["descending", "arch", "wave", "ascending"] = "wave"
    transform: str = "identity"
    notes: list[MotifNote] = Field(default_factory=list)


class HarmonyPlan(BaseModel):
    chords: list[str] = Field(default_factory=list)
    roots: list[int] = Field(default_factory=list)
    bass_pitches: list[int] = Field(default_factory=list)
    counterpoint: list[MotifNote] = Field(default_factory=list)
    provider: Literal["rule", "notochord"] = "rule"
    fallback_reason: str = ""


class OrchestrationPlan(BaseModel):
    role_density: dict[str, float] = Field(default_factory=dict)
    role_velocity: dict[str, int] = Field(default_factory=dict)
    enabled_roles: list[str] = Field(default_factory=list)
    stem_gain: float = Field(default=0.0, ge=0.0, le=1.0)
    magenta_audio_gain: float = Field(default=0.0, ge=0.0, le=1.0)


class CanonicalMusicEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str = ""
    sequence: int = Field(default=0, ge=0)
    timestamp: float = Field(default_factory=time.time)
    source: str = "rule"
    role: str
    track_id: str
    type: EventType
    bar: int = Field(default=0, ge=0)
    beat: float = Field(default=0.0, ge=0.0)
    pitch: int | None = Field(default=None, ge=0, le=127)
    velocity: int | None = Field(default=None, ge=0, le=127)
    duration_ms: int | None = Field(default=None, ge=0)
    channel: int | None = Field(default=None, ge=1, le=16)
    control: str | None = None
    value: float | None = None
    latency_ms: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeLogEntry(BaseModel):
    sequence: int = Field(default=0, ge=0)
    timestamp: float = Field(default_factory=time.time)
    session_id: str = ""
    level: Literal["debug", "info", "warning", "error"] = "info"
    category: Literal[
        "input", "context", "policy", "form", "motif", "melody", "harmony",
        "orchestration", "output", "model", "health", "test", "system",
    ] = "system"
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
