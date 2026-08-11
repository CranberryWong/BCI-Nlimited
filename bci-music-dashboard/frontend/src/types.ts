export type EmotionLabel = 'joy' | 'calm' | 'neutral' | 'tense' | 'sad';
export type TrackRole = 'melody' | 'chord' | 'bass' | 'drum' | 'cymbal' | 'pad' | 'fx';
export type SystemMode = 'MIRROR' | 'ENGAGING';
export type CompositionMode = 'theme' | 'motif' | 'hybrid' | 'anchored' | 'generative' | 'portrait';

export interface EmotionState {
  valence_class: number;
  arousal_class: number;
  valence_prob: number;
  arousal_prob: number;
  valence_norm: number;
  arousal_norm: number;
  confidence: number;
  label: EmotionLabel;
  timestamp: number;
  source: 'real_model' | 'simulator' | 'osc_input';
}

export interface MusicEvent {
  timestamp: number;
  track_id: string;
  type: string;
  pitch: number | null;
  velocity: number | null;
  duration_ms: number | null;
  channel: number | null;
  address: string | null;
  args: unknown[];
}

export interface MusicSegment {
  id: string;
  emotion: EmotionLabel;
  previous_emotion: EmotionLabel;
  bpm: number;
  bars: number;
  beats_per_bar: number;
  source: 'model' | 'rule' | 'theme' | 'motif' | 'portrait' | 'hybrid';
  form_section: 'intro' | 'theme' | 'variation' | 'development' | 'climax' | 'return' | 'coda';
  phrase_id: string;
  theme_id: string;
  motif_id: string;
  motif_title: string;
  portrait: EmotionLabel | null;
  theme_similarity: number;
  harmony: string[];
  transition_type: string;
  ornamented_beats: number[];
  actual_max_voices: number;
  harmony_note_count: number;
  arpeggio_note_count: number;
  notochord_modified_count: number;
  generation_ms: number;
}

export interface ThemeSummary {
  id: string;
  title: string;
  home_key: string;
  mode: string;
  bars: number;
  license: Record<string, string>;
}

export interface MusicParams {
  tempo: number;
  density: number;
  velocity: number;
  register: 'low' | 'mid' | 'mid_high' | 'high' | 'wide';
  scale: string;
  mode: string;
  instruments: Record<string, number>;
  reverb: number;
  delay: number;
  rhythm_complexity: number;
  brightness: number;
  tension: number;
}

export interface SmoothedEmotion {
  label: EmotionLabel;
  valence_norm: number;
  arousal_norm: number;
  confidence: number;
}

export interface MusicGeneratorStatus {
  running: boolean;
  mode: CompositionMode;
  system_mode: SystemMode;
  composition_mode: CompositionMode;
  current_portrait_asset_id?: string;
  current_portrait_asset_title?: string;
  portrait_role?: 'loop' | 'tension' | 'release' | 'sketch' | '';
  portrait_harmony_enabled?: boolean;
  portrait_harmony_arpeggio_enabled?: boolean;
  notochord_tracks?: Record<string, { enabled: boolean; mode: string; available: boolean }>;
  notochord_track_counts?: Record<string, number>;
  base_bpm?: number;
  effective_bpm?: number;
  next_target_bpm?: number | null;
  bass_note_count?: number;
  drum_note_count?: number;
  cymbal_note_count?: number;
  current_harmony?: string;
  current_harmony_index?: number | null;
  harmony_progression?: string[];
  available_portrait_assets?: Array<{ id: string; title: string; emotion: string; role: string; meter: string; bars: number; bpm: number }>;
  portrait_library_errors?: string[];
  xylophone_same_key_minimum_interval_seconds?: number;
  xylophone_suppressed_count?: number;
  initial_emotion_ready?: boolean;
  required_initial_samples?: number;
  active_portrait_emotion?: EmotionLabel | null;
  pending_portrait_emotion?: EmotionLabel | null;
  next_portrait_role?: 'loop' | 'tension' | 'release';
  model_provider: 'notochord' | 'local' | 'rule';
  model_available: boolean;
  model_loaded: boolean;
  model_detail: string;
  window_seconds: number;
  window_samples: number;
  fast_window_seconds: number;
  fast_window_samples: number;
  fast_window_emotion: EmotionLabel;
  slow_window_emotion: EmotionLabel;
  current_emotion: EmotionLabel;
  candidate_emotion: EmotionLabel;
  current_portrait: EmotionLabel;
  current_motif_id: string | null;
  current_motif_title: string | null;
  motif_approved: boolean;
  segment_source: 'theme' | 'motif' | 'hybrid' | string;
  transition_strategy: string;
  transition_preparing: boolean;
  transition_progress: number;
  raw_emotion: Partial<EmotionState> | null;
  smoothed_emotion: SmoothedEmotion | null;
  music_params: MusicParams;
  engaging_stage: string | null;
  stage_elapsed_sec: number;
  stage_progress: number;
  target_state_progress: number;
  current_segment_id: string | null;
  theme_similarity: number | null;
  actual_max_voices: number;
  harmony_note_count: number;
  arpeggio_note_count: number;
  notochord_modified_count: number;
  next_segment_ready: boolean;
  bpm: number;
  remaining_seconds: number | null;
  last_generation_ms: number;
  fallback_count: number;
  generation_error: string;
  experience_elapsed_seconds: number;
  theme_id: string;
  theme_title: string | null;
  available_themes: ThemeSummary[];
  form_section: MusicSegment['form_section'] | null;
  phrase_id: string | null;
  phrase_index: number;
  total_phrases: number;
  next_boundary: string;
  theme_recognition: number;
  generation_freedom: number;
}

export interface PresetsTestingStatus {
  running: boolean;
  type: 'presets_testing';
  initial_emotion_ready: boolean;
  raw_preset_id: string;
  raw_preset_path: string;
  raw_meter: string;
  raw_bpm: number | null;
  window_start_beat: number;
  window_bars: number;
  current_bpm: number;
  current_emotion: EmotionLabel;
  source_locked: boolean;
  rule_percussion_count: number;
  notochord_percussion_count: number;
  fallback_count: number;
  generation_error: string;
}

export interface NotoTestingStatus {
  running: boolean;
  type: 'noto_testing';
  phase: 'stopped' | 'waiting_for_emotion' | 'notochord_ensemble' | 'error';
  initial_emotion_ready: boolean;
  initial_asset_id: string;
  initial_asset_title: string;
  initial_asset_path: string;
  current_emotion: EmotionLabel;
  profile_scale: string;
  profile_chord_quality: string;
  current_bpm: number;
  window_bars: number;
  segment_index: number;
  notochord_event_count: number;
  notochord_track_counts: Record<string, number>;
  model_detail: string;
  generation_error: string;
}

export interface TrackConfig {
  id: string;
  name: string;
  enabled: boolean;
  compute_enabled: boolean;
  role: TrackRole;
  instrument: string;
  output_type: 'midi' | 'osc';
  target_ip: string;
  target_port: number;
  midi_channel: number;
  midi_program: number | null;
  root_note: string;
  scale: string;
  pitch_range: [number, number];
  velocity_range: [number, number];
  bpm: number | 'auto';
  density: number;
  polyphony: number;
  voicing_enabled?: boolean;
  voicing_density?: number;
  notochord_revoice_rate?: number;
  notochord_enabled?: boolean;
  notochord_mode?: 'off' | 'revoice' | 'fill';
  notochord_rate?: number;
  notochord_instrument?: number | null;
  arpeggio_enabled?: boolean;
  arpeggio_density?: number;
  arpeggio_rate?: '1/8' | '1/16';
  arpeggio_max_group_notes?: number;
  arpeggio_notochord_rate?: number;
  delay_ms: number;
  note_length_ms: number;
  humanize: number;
  mapping: Record<string, number>;
  [key: string]: unknown;
}

export interface MusicConfig {
  global: Record<string, string | number>;
  emotion_profiles: Record<string, EmotionProfile>;
  default_tracks: TrackConfig[];
  music_parameter_schema: Record<string, { min?: number; max?: number; type: string; editable: boolean }>;
  default_schema?: Record<string, unknown>;
}

export interface EmotionProfile {
  label_zh: string;
  scale: string;
  bpm_range: number[];
  pitch_range: number[];
  velocity_range: number[];
  density_range: number[];
  delay_ms_range: number[];
  chord_quality: string;
  brightness: number;
  tension: number;
  [key: string]: string | number | number[] | boolean;
}

export interface InputSourceStatus {
  source_id: string;
  kind: string;
  health: string;
  quality: number;
  age_seconds: number | null;
  last_sequence: number | null;
  detail?: string;
}

export interface ContextFrame {
  timestamp: number;
  valence: number;
  arousal: number;
  bci_confidence: number;
  heart_rate: number | null;
  motion: number | null;
  ambient_light: number | null;
  degraded: boolean;
}

export interface AdaptiveIntent {
  valence: number;
  energy: number;
  tension: number;
  density: number;
  brightness: number;
  pulse: number;
  complexity: number;
  register_band: string;
  articulation: string;
  spatial_width: number;
  transition_urgency: number;
  frozen_motif: boolean;
}

export interface RuntimeLogEntry {
  sequence: number;
  timestamp: number;
  level: string;
  category: string;
  message: string;
  data: Record<string, unknown>;
}

export interface AdaptiveRuntimeStatus {
  running: boolean;
  session_id: string | null;
  config_locked: boolean;
  started_at: number | null;
  transport: { running: boolean; bpm: number; bar: number; beat: number; phase: number };
  context: ContextFrame | null;
  intent: AdaptiveIntent | null;
  form: { section_id: string; role: string; section_index: number; phrase_index: number; phrase_in_section: number; section_count: number; is_final: boolean };
  tonal: Record<string, unknown> | null;
  motif: Record<string, unknown> | null;
  harmony: Record<string, unknown> | null;
  orchestration: Record<string, unknown> | null;
  prompt: string;
  magenta: { connected: boolean; detail: string; failures: number; health: Record<string, unknown>; url: string };
  fallback_count: number;
  outputs: Record<string, unknown>;
  inputs: InputSourceStatus[];
  sensor_osc: { running: boolean; host: string; port: number; detail: string };
  auxiliary_simulator: { running: boolean };
  recent_logs: RuntimeLogEntry[];
}
