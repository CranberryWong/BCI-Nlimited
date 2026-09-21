import { defineStore } from 'pinia';
import { api } from '../api/client';
import { openRealtime } from '../api/websocket';
import type { AdaptiveRuntimeStatus, RuntimeLogEntry } from '../types';

export const useAdaptiveStore = defineStore('adaptive', {
  state: () => ({
    status: null as AdaptiveRuntimeStatus | null,
    modules: {} as Record<string, Record<string, unknown>>,
    logs: [] as RuntimeLogEntry[],
    socket: null as WebSocket | null,
    diagnostics: null as Record<string, unknown> | null,
  }),
  actions: {
    async init() {
      const [status, config] = await Promise.all([api.get('/runtime/status'), api.get('/config')]);
      this.status = status.data as AdaptiveRuntimeStatus;
      this.modules = config.data.modules;
      this.logs = this.status.recent_logs || [];
      if (this.socket) return;
      this.socket = openRealtime((message) => {
        if (!('kind' in message) && message.version === 'v1') {
          const next = message.payload?.status as AdaptiveRuntimeStatus | undefined;
          if (next) {
            this.status = next;
            this.logs = next.recent_logs || this.logs;
          }
        }
      });
    },
    async refresh() {
      this.status = (await api.get('/runtime/status')).data as AdaptiveRuntimeStatus;
      this.logs = this.status.recent_logs || [];
    },
    async start() {
      this.status = (await api.post('/performance/start')).data as AdaptiveRuntimeStatus;
    },
    async stop() {
      this.status = (await api.post('/performance/stop')).data as AdaptiveRuntimeStatus;
      await this.loadConfig();
    },
    async runDiagnostics() {
      this.diagnostics = (await api.post('/diagnostics/run')).data;
      await this.refresh();
    },
    async startAuxiliarySimulator() {
      await api.post('/inputs/simulator/start');
      await this.refresh();
    },
    async stopAuxiliarySimulator() {
      await api.post('/inputs/simulator/stop');
      await this.refresh();
    },
    async loadConfig() {
      const response = await api.get('/config');
      this.modules = response.data.modules;
      if (this.status) this.status.config_locked = response.data.locked;
    },
    async saveModule(module: string, config: Record<string, unknown>) {
      const response = await api.put(`/config/${module}`, config);
      this.modules[module] = response.data.config;
      await this.refresh();
    },
    async resetModule(module: string) {
      const response = await api.post(`/config/${module}/reset`);
      this.modules[module] = response.data.config;
      await this.refresh();
    },
  },
});
