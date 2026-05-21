import { defineStore } from 'pinia';
import { api } from '../api/client';
import { openRealtime } from '../api/websocket';
import type { EmotionState, MusicEvent } from '../types';

export const useEmotionStore = defineStore('emotion', {
  state: () => ({
    latest: null as EmotionState | null,
    history: [] as EmotionState[],
    events: [] as MusicEvent[],
    status: {} as Record<string, unknown>,
    socket: null as WebSocket | null,
  }),
  actions: {
    async init() {
      this.status = (await api.get('/control/status')).data;
      if (this.socket) return;
      this.socket = openRealtime((message) => {
        this.status = message.status;
        if (message.kind === 'realtime') {
          this.latest = message.emotion;
          this.history.push(message.emotion);
          this.history = this.history.slice(-1200);
          this.events.unshift(...message.music_events.reverse());
          this.events = this.events.slice(0, 100);
        }
      });
    },
    async startSimulator() {
      this.status = (await api.post('/control/start-simulator')).data;
    },
    async stopSimulator() {
      this.status = (await api.post('/control/stop-simulator')).data;
    },
    async startModel() {
      this.status = (await api.post('/control/start-model')).data;
    },
    async stopModel() {
      this.status = (await api.post('/control/stop-model')).data;
    },
  },
});
