import { defineStore } from 'pinia';
import { api } from '../api/client';

export const useOutputsStore = defineStore('outputs', {
  state: () => ({ midi: { mode: 'mock', ports: [] as string[], detail: '' } }),
  actions: {
    async loadMidi() {
      this.midi = (await api.get('/outputs/midi-ports')).data;
    },
    async test(trackId: string) {
      return (await api.post('/outputs/test', { track_id: trackId })).data;
    },
  },
});
