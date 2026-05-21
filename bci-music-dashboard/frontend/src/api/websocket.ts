import type { EmotionState, MusicEvent } from '../types';

export type RealtimeMessage =
  | { kind: 'status'; status: Record<string, unknown> }
  | { kind: 'realtime'; emotion: EmotionState; music_events: MusicEvent[]; status: Record<string, unknown> };

export function openRealtime(onMessage: (message: RealtimeMessage) => void) {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${scheme}://${location.host}/ws/realtime`);
  socket.addEventListener('message', (event) => onMessage(JSON.parse(event.data)));
  return socket;
}
