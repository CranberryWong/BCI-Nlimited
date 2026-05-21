export type EmotionLabel = 'joy' | 'calm' | 'neutral' | 'tense' | 'sad';
export type TrackRole = 'melody' | 'chord' | 'bass' | 'drum' | 'cymbal' | 'pad' | 'fx';

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
