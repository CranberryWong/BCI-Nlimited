import { defineStore } from 'pinia';
import { api } from '../api/client';
import type { MusicConfig, TrackConfig, TrackRole } from '../types';

const roleName: Record<TrackRole, string> = {
  melody: 'Melody',
  chord: 'Chord',
  bass: 'Bass',
  drum: 'Drum',
  cymbal: 'Cymbal',
  pad: 'Pad',
  fx: 'FX',
};

export const useTracksStore = defineStore('tracks', {
  state: () => ({
    config: null as MusicConfig | null,
    tracks: [] as TrackConfig[],
  }),
  actions: {
    async loadConfig() {
      this.config = (await api.get('/music/config')).data;
      this.tracks = this.config?.default_tracks ?? [];
    },
    async applyConfig(config: MusicConfig) {
      const applied = (await api.put('/music/config', config)).data as MusicConfig;
      this.config = applied;
      this.tracks = applied.default_tracks;
    },
    async resetConfig() {
      const reset = (await api.post('/music/config/reset')).data as MusicConfig;
      this.config = reset;
      this.tracks = reset.default_tracks;
    },
    async patchTrack(track: TrackConfig) {
      const updated = (await api.patch(`/tracks/${track.id}`, track)).data as TrackConfig;
      this.tracks = this.tracks.map((item) => (item.id === updated.id ? updated : item));
      if (this.config) this.config.default_tracks = this.tracks;
    },
    async resetTrack(id: string) {
      const updated = (await api.post(`/tracks/${id}/reset`)).data as TrackConfig;
      this.tracks = this.tracks.map((item) => (item.id === updated.id ? updated : item));
    },
    async duplicate(id: string) {
      this.tracks.push((await api.post(`/tracks/${id}/duplicate`)).data);
    },
    async remove(id: string) {
      await api.delete(`/tracks/${id}`);
      this.tracks = this.tracks.filter((track) => track.id !== id);
    },
    async add(role: TrackRole) {
      const seed = this.tracks.find((track) => track.role === role) ?? this.tracks[0];
      const created: TrackConfig = {
        ...(seed ?? {
          target_ip: '127.0.0.1',
          target_port: 57120,
          midi_channel: role === 'drum' || role === 'cymbal' ? 10 : 1,
          midi_program: 0,
          root_note: 'auto',
          scale: 'auto',
          pitch_range: [48, 84],
          velocity_range: [30, 100],
          bpm: 'auto',
          density: 0.5,
          delay_ms: 0,
          note_length_ms: 250,
          humanize: 0.1,
          mapping: { valence_to_pitch: 0.5, arousal_to_velocity: 0.5, arousal_to_density: 0.5, probability_to_randomness: -0.4 },
        }),
        id: `${role}-${crypto.randomUUID().slice(0, 8)}`,
        name: `${roleName[role]} Track`,
        role,
        instrument: role,
        enabled: true,
        compute_enabled: true,
        output_type: 'osc',
      } as TrackConfig;
      this.tracks.push((await api.post('/tracks', created)).data);
    },
  },
});
