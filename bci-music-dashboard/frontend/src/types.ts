export type EmotionLabel = 'joy' | 'calm' | 'neutral' | 'tense' | 'sad';
export type TrackRole = 'melody' | 'chord' | 'bass' | 'drum' | 'cymbal' | 'pad' | 'fx';
export type SystemMode = 'MIRROR' | 'ENGAGING';
export type CompositionMode = 'theme' | 'motif' | 'hybrid' | 'anchored' | 'generative';

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
  source: 'model' | 'rule' | 'theme' | 'motif' | 'hybrid';
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
