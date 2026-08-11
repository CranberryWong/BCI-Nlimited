import { defineStore } from 'pinia';
import { api } from '../api/client';
import { openRealtime } from '../api/websocket';
import type { EmotionState, MusicEvent, MusicGeneratorStatus, MusicSegment, NotoTestingStatus, PresetsTestingStatus } from '../types';

export const useEmotionStore = defineStore('emotion', {
  state: () => ({
    latest: null as EmotionState | null,
    history: [] as EmotionState[],
    events: [] as MusicEvent[],
    status: {} as Record<string, unknown>,
    generator: null as MusicGeneratorStatus | null,
    presetsTesting: null as PresetsTestingStatus | null,
    notoTesting: null as NotoTestingStatus | null,
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
      const initialPresets = this.status.presets_testing;
      if (initialPresets && typeof initialPresets === 'object') this.presetsTesting = initialPresets as PresetsTestingStatus;
      const initialNoto = this.status.noto_testing;
      if (initialNoto && typeof initialNoto === 'object') this.notoTesting = initialNoto as NotoTestingStatus;
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
          const presets = message.status.presets_testing;
          if (presets && typeof presets === 'object') this.presetsTesting = presets as PresetsTestingStatus;
          const noto = message.status.noto_testing;
          if (noto && typeof noto === 'object') this.notoTesting = noto as NotoTestingStatus;
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
        } else if (message.kind === 'presets_testing_segment_started') {
          this.presetsTesting = message.presets_testing as PresetsTestingStatus;
        } else if (message.kind === 'noto_testing_initial_started' || message.kind === 'noto_testing_segment_started' || message.kind === 'noto_testing_error') {
          this.notoTesting = message.noto_testing as NotoTestingStatus;
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
    async startPresetsTesting() {
      this.presetsTesting = (await api.post('/control/start-presets-testing')).data as PresetsTestingStatus;
    },
    async stopPresetsTesting() {
      this.presetsTesting = (await api.post('/control/stop-presets-testing')).data as PresetsTestingStatus;
    },
    async startNotoTesting() {
      this.notoTesting = (await api.post('/control/start-noto-testing')).data as NotoTestingStatus;
    },
    async stopNotoTesting() {
      this.notoTesting = (await api.post('/control/stop-noto-testing')).data as NotoTestingStatus;
    },
    async updatePortraitHarmony(enabled: boolean) {
      this.generator = (await api.patch('/music-generator/settings', {
        portrait_harmony_enabled: enabled,
      })).data;
    },
    async updatePortraitHarmonyArpeggio(enabled: boolean) {
      this.generator = (await api.patch('/music-generator/settings', {
        portrait_harmony_arpeggio_enabled: enabled,
      })).data;
    },
  },
});
