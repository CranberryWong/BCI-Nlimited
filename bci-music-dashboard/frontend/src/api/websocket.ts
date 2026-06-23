import type { EmotionState, MusicEvent, MusicGeneratorStatus, MusicSegment } from '../types';

export type RealtimeMessage =
  | { kind: 'status'; status: Record<string, unknown> }
  | { kind: 'realtime'; emotion: EmotionState; music_events: MusicEvent[]; status: Record<string, unknown> }
  | { kind: 'music_event'; music_event: MusicEvent; status: Record<string, unknown> }
  | { kind: 'segment_generated' | 'segment_started'; segment: MusicSegment; status: MusicGeneratorStatus }
  | { kind: 'phrase_started'; phrase_id: string; form_section: string; segment: MusicSegment; status: MusicGeneratorStatus }
  | { kind: 'form_section_changed' | 'harmony_changed' | 'theme_quoted' | 'climax_changed' | 'experience_completed' | 'mode_changed' | 'engaging_stage_changed' | 'music_params_changed'; status: MusicGeneratorStatus; [key: string]: unknown }
  | { kind: 'generator_status'; status: MusicGeneratorStatus };

export function openRealtime(onMessage: (message: RealtimeMessage) => void) {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${scheme}://${location.host}/ws/realtime`);
  socket.addEventListener('message', (event) => onMessage(JSON.parse(event.data)));
  return socket;
}
