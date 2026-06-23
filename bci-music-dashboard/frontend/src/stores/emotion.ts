import { defineStore } from 'pinia';
import { api } from '../api/client';
import { openRealtime } from '../api/websocket';
import type { CompositionMode, EmotionState, MusicEvent, MusicGeneratorStatus, MusicSegment, SystemMode } from '../types';

export const useEmotionStore = defineStore('emotion', {
  state: () => ({
    latest: null as EmotionState | null,
    history: [] as EmotionState[],
    events: [] as MusicEvent[],
    status: {} as Record<string, unknown>,
    generator: null as MusicGeneratorStatus | null,
    currentSegment: null as MusicSegment | null,
    nextSegment: null as MusicSegment | null,
    socket: null as WebSocket | null,
  }),
  actions: {
    async init() {
      this.status = (await api.get('/control/status')).data;
      const initialGenerator = this.status.music_generator;
      if (initialGenerator && typeof initialGenerator === 'object') {
        this.generator = initialGenerator as MusicGeneratorStatus;
      }
      if (this.socket) return;
      this.socket = openRealtime((message) => {
        if (message.kind === 'realtime') {
          this.status = message.status;
          this.latest = message.emotion;
          this.history.push(message.emotion);
          this.history = this.history.slice(-1200);
          this.events.unshift(...message.music_events.reverse());
          this.events = this.events.slice(0, 100);
          const generator = message.status.music_generator;
          if (generator && typeof generator === 'object') this.generator = generator as MusicGeneratorStatus;
        } else if (message.kind === 'music_event') {
          this.status = message.status;
          this.events.unshift(message.music_event);
          this.events = this.events.slice(0, 100);
        } else if (message.kind === 'segment_generated') {
          this.nextSegment = message.segment;
          this.generator = message.status;
        } else if (message.kind === 'segment_started') {
          this.currentSegment = message.segment;
          this.nextSegment = null;
          this.generator = message.status;
        } else if (message.kind === 'generator_status') {
          this.generator = message.status;
        } else if (
          ['phrase_started', 'form_section_changed', 'harmony_changed', 'theme_quoted', 'climax_changed', 'experience_completed', 'mode_changed', 'engaging_stage_changed', 'music_params_changed']
            .includes(message.kind)
        ) {
          this.generator = message.status as MusicGeneratorStatus;
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
    async startMusicGenerator() {
      this.generator = (await api.post('/control/start-music-generator')).data;
    },
    async stopMusicGenerator() {
      this.generator = (await api.post('/control/stop-music-generator')).data;
    },
    async reloadMusicModel() {
      this.generator = (await api.post('/control/reload-music-model')).data;
    },
    async selectMusicTheme(themeId: string) {
      this.generator = (await api.put(`/music-generator/theme/${themeId}`)).data;
    },
    async randomMusicTheme() {
      this.generator = (await api.post('/music-generator/random-theme')).data;
    },
    async updateMusicGeneratorSettings(settings: {
      theme_recognition: number;
      generation_freedom: number;
      composition_mode?: CompositionMode;
    }) {
      this.generator = (await api.patch('/music-generator/settings', settings)).data;
    },
    async setMusicGeneratorMode(systemMode: SystemMode) {
      this.generator = (await api.post('/music-generator/mode', { system_mode: systemMode })).data;
    },
  },
});
