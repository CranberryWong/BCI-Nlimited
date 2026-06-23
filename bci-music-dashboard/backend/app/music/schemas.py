from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EmotionLabel = Literal["joy", "calm", "neutral", "tense", "sad"]
SystemMode = Literal["MIRROR", "ENGAGING"]
FormSection = Literal["intro", "theme", "variation", "development", "climax", "return", "coda"]
TrackRole = Literal["melody", "chord", "bass", "drum", "cymbal", "pad", "fx"]
OutputType = Literal["midi", "osc"]
MusicEventType = Literal["note_on", "note_off", "control", "osc"]
VoiceRole = Literal["theme", "harmony", "ornament"]
NoteGenerator = Literal["theme", "rule", "notochord"]
CompositionMode = Literal["theme", "motif", "hybrid", "anchored", "generative"]


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


class SegmentNote(BaseModel):
    beat: float = Field(ge=0.0)
    duration_beats: float = Field(gt=0.0)
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(ge=1, le=127)
    track_id: str
    channel: int = Field(ge=1, le=16)
    voice_role: VoiceRole | None = None
    generated_by: NoteGenerator = "rule"


class MusicSegment(BaseModel):
    id: str
    emotion: EmotionLabel
    previous_emotion: EmotionLabel
    bpm: int = Field(ge=30, le=220)
    bars: int = Field(default=4, ge=1, le=16)
    beats_per_bar: int = Field(default=4, ge=1, le=12)
    root_note: str = "C"
    scale: str = "gong"
    source: Literal["model", "rule", "theme", "motif", "hybrid"]
    form_section: FormSection = "theme"
    phrase_id: str = ""
    theme_id: str = ""
    motif_id: str = ""
    motif_title: str = ""
    portrait: EmotionLabel | None = None
    theme_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    harmony: list[str] = Field(default_factory=list)
    transition_type: str = "continue"
    from_emotion: EmotionLabel | None = None
    to_emotion: EmotionLabel | None = None
    transition_progress: float = Field(default=0.0, ge=0.0, le=1.0)
    transition_strategy: str = ""
    ornamented_beats: list[float] = Field(default_factory=list)
    actual_max_voices: int = Field(default=1, ge=1, le=8)
    harmony_note_count: int = Field(default=0, ge=0)
    arpeggio_note_count: int = Field(default=0, ge=0)
    notochord_modified_count: int = Field(default=0, ge=0)
    generated_at: float = Field(default_factory=time.time)
    generation_ms: float = Field(default=0.0, ge=0.0)
    notes: list[SegmentNote] = Field(default_factory=list)

    @property
    def total_beats(self) -> int:
        return self.bars * self.beats_per_bar

    @property
    def duration_seconds(self) -> float:
        return self.total_beats * 60.0 / self.bpm


class MusicParams(BaseModel):
    tempo: int = Field(default=84, ge=30, le=220)
    density: float = Field(default=0.5, ge=0.0, le=1.0)
    velocity: float = Field(default=0.5, ge=0.0, le=1.0)
    register: Literal["low", "mid", "mid_high", "high", "wide"] = "mid"
    scale: str = "gong"
    mode: str = "pentatonic"
    instruments: dict[str, float] = Field(default_factory=dict)
    reverb: float = Field(default=0.25, ge=0.0, le=1.0)
    delay: float = Field(default=0.1, ge=0.0, le=1.0)
    rhythm_complexity: float = Field(default=0.35, ge=0.0, le=1.0)
    brightness: float = Field(default=0.5, ge=0.0, le=1.0)
    tension: float = Field(default=0.1, ge=0.0, le=1.0)


class ModeTargetState(BaseModel):
    valence: float = Field(default=0.85, ge=0.0, le=1.0)
    arousal: float = Field(default=0.65, ge=0.0, le=1.0)
    tension: float = Field(default=0.2, ge=0.0, le=1.0)
    agency: float = Field(default=0.8, ge=0.0, le=1.0)


class EngagingStageConfig(BaseModel):
    name: str
    start: float = Field(ge=0.0)
    end: float = Field(gt=0.0)


class MirrorModeConfig(BaseModel):
    smoothing: float = Field(default=0.25, ge=0.0, le=1.0)
    emotion_mappings: dict[EmotionLabel, MusicParams] = Field(default_factory=dict)


class EngagingModeConfig(BaseModel):
    duration_sec: int = Field(default=240, ge=60, le=600)
    smoothing: float = Field(default=0.18, ge=0.0, le=1.0)
    target_state: ModeTargetState = Field(default_factory=ModeTargetState)
    stages: list[EngagingStageConfig] = Field(default_factory=list)
    initial_emotion_paths: dict[EmotionLabel, list[str]] = Field(default_factory=dict)


class SystemModesConfig(BaseModel):
    MIRROR: MirrorModeConfig = Field(default_factory=MirrorModeConfig)
    ENGAGING: EngagingModeConfig = Field(default_factory=EngagingModeConfig)


class MusicGeneratorConfig(BaseModel):
    enabled: bool = False
    window_seconds: float = Field(default=16.0, ge=4.0, le=120.0)
    fast_window_seconds: float = Field(default=4.0, ge=1.0, le=30.0)
    minimum_samples: int = Field(default=4, ge=1, le=120)
    bars: int = Field(default=8, ge=1, le=16)
    beats_per_bar: int = Field(default=4, ge=1, le=12)
    candidate_count: int = Field(default=4, ge=1, le=16)
    inference_timeout_seconds: float = Field(default=2.0, ge=0.1, le=30.0)
    lookahead_beats: float = Field(default=4.0, ge=1.0, le=16.0)
    max_bpm_step: int = Field(default=6, ge=1, le=30)
    system_mode: SystemMode = "ENGAGING"
    composition_mode: CompositionMode = "motif"
    target_duration_seconds: int = Field(default=240, ge=60, le=600)
    theme_id: str = "random"
    theme_recognition: float = Field(default=0.65, ge=0.0, le=1.0)
    generation_freedom: float = Field(default=0.35, ge=0.0, le=1.0)
    fallback_strategy: Literal["rule_variation"] = "rule_variation"
    model_provider: Literal["auto", "local", "notochord", "rule"] = "auto"
    model_path: str = "models/music/latest.pt"
    model_config_path: str = "models/music/model_config.json"
    notochord_checkpoint: str = "~/Library/Application Support/Notochord/notochord-latest.ckpt"
    notochord_device: Literal["cpu", "mps", "auto"] = "cpu"
    notochord_instrument: int = Field(default=14, ge=1, le=128)
    system_modes: SystemModesConfig = Field(default_factory=SystemModesConfig)
    emotion_bpm: dict[EmotionLabel, int] = Field(
        default_factory=lambda: {
            "joy": 108,
            "calm": 68,
            "neutral": 84,
            "tense": 120,
            "sad": 60,
        }
    )


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
    system_modes: SystemModesConfig = Field(default_factory=SystemModesConfig)

    model_config = ConfigDict(populate_by_name=True)

    def as_api(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
