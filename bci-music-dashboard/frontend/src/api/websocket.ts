import type { AdaptiveRuntimeStatus, EmotionState, MusicEvent, MusicGeneratorStatus, MusicSegment, NotoTestingStatus, PresetsTestingStatus } from '../types';

export type RealtimeMessage =
  | { kind: 'status'; status: Record<string, unknown> }
  | { kind: 'realtime'; emotion: EmotionState; music_events: MusicEvent[]; status: Record<string, unknown> }
  | { kind: 'music_event'; music_event: MusicEvent; status: Record<string, unknown> }
  | { kind: 'segment_generated' | 'segment_started'; segment: MusicSegment; status: MusicGeneratorStatus }
  | { kind: 'phrase_started'; phrase_id: string; form_section: string; segment: MusicSegment; status: MusicGeneratorStatus }
  | { kind: 'form_section_changed' | 'harmony_changed' | 'theme_quoted' | 'climax_changed' | 'experience_completed' | 'mode_changed' | 'engaging_stage_changed' | 'music_params_changed'; status: MusicGeneratorStatus; [key: string]: unknown }
  | { kind: 'generator_status'; status: MusicGeneratorStatus }
  | { kind: 'presets_testing_segment_started'; segment: MusicSegment; presets_testing: PresetsTestingStatus }
  | { kind: 'noto_testing_initial_started'; segment: MusicSegment; noto_testing: NotoTestingStatus }
  | { kind: 'noto_testing_segment_started'; segment: MusicSegment; noto_testing: NotoTestingStatus }
  | { kind: 'noto_testing_error'; noto_testing: NotoTestingStatus }
  | { version: 'v1'; type: string; seq: number; timestamp: number; session_id: string | null; payload: { status?: AdaptiveRuntimeStatus; event?: Record<string, unknown>; [key: string]: unknown } };

export function openRealtime(onMessage: (message: RealtimeMessage) => void) {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${scheme}://${location.host}/ws/realtime`);
  socket.addEventListener('message', (event) => onMessage(JSON.parse(event.data)));
  return socket;
}
