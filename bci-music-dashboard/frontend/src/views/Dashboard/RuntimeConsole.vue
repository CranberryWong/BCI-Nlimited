<template>
  <section class="surface runtime-console">
    <header class="runtime-header">
      <div>
        <h2>Adaptive Performance Runtime</h2>
        <p>BCI 主导 · 多源上下文辅助 · 统一 Transport / MIDI / OSC</p>
      </div>
      <div class="runtime-actions">
        <n-tag :type="status?.running ? 'success' : 'default'">{{ status?.running ? '演出运行中 · 配置已锁定' : '演出已停止' }}</n-tag>
        <n-button :disabled="status?.running" type="primary" @click="$emit('start')">开始演出</n-button>
        <n-button :disabled="!status?.running" type="error" @click="$emit('stop')">停止 / All Notes Off</n-button>
        <n-button @click="$emit('diagnostics')">运行诊断</n-button>
        <n-button v-if="!status?.auxiliary_simulator.running" @click="$emit('start-simulator')">辅助输入模拟</n-button>
        <n-button v-else @click="$emit('stop-simulator')">停止辅助模拟</n-button>
      </div>
    </header>

    <div class="runtime-grid">
      <article class="runtime-card">
        <h3>Transport 与曲式</h3>
        <strong>{{ Math.round(status?.transport.bpm || 0) }} BPM</strong>
        <span>Bar {{ status?.transport.bar || 1 }} · Beat {{ (status?.transport.beat || 1).toFixed(2) }}</span>
        <span>Section {{ status?.form.section_id || 'Intro' }} · Phrase {{ status?.form.phrase_index || 0 }}</span>
        <span>Session {{ status?.session_id || '—' }}</span>
      </article>

      <article class="runtime-card">
        <h3>Context → MusicIntent</h3>
        <span>Valence {{ format(status?.intent?.valence) }} · Energy {{ format(status?.intent?.energy) }}</span>
        <span>Tension {{ format(status?.intent?.tension) }} · Density {{ format(status?.intent?.density) }}</span>
        <span>Brightness {{ format(status?.intent?.brightness) }} · Pulse {{ format(status?.intent?.pulse) }}</span>
        <span :class="{ warning: status?.context?.degraded }">BCI confidence {{ format(status?.context?.bci_confidence) }}{{ status?.context?.degraded ? ' · degraded' : '' }}</span>
      </article>

      <article class="runtime-card">
        <h3>Magenta / 降级</h3>
        <span :class="{ warning: !status?.magenta.connected }">{{ status?.magenta.connected ? 'MRT2 已连接' : '规则续演' }}</span>
        <span>{{ status?.magenta.detail || '等待工作进程' }}</span>
        <span>Fallback {{ status?.fallback_count || 0 }}</span>
        <span class="prompt" :title="status?.prompt">{{ status?.prompt || '—' }}</span>
      </article>

      <article class="runtime-card inputs-card">
        <h3>输入新鲜度</h3>
        <div v-if="inputRows.length" class="input-row" v-for="item in inputRows" :key="item.source_id">
          <span>{{ item.source_id }}</span>
          <n-tag size="small" :type="item.health === 'healthy' ? 'success' : item.health === 'missing' ? 'default' : 'warning'">{{ item.health }}</n-tag>
          <span>q {{ item.quality.toFixed(2) }}</span>
          <span>{{ item.age_seconds == null ? '—' : `${item.age_seconds.toFixed(1)}s` }}</span>
        </div>
        <span v-else>等待输入</span>
      </article>
    </div>

    <header class="log-header">
      <h3>统一 Runtime Log</h3>
      <span>OSC sensor {{ status?.sensor_osc.running ? `${status.sensor_osc.host}:${status.sensor_osc.port}` : 'unavailable' }}</span>
    </header>
    <div class="log-stream">
      <div v-for="item in logs.slice().reverse().slice(0, 120)" :key="item.sequence" class="log-row">
        <time>{{ new Date(item.timestamp * 1000).toLocaleTimeString() }}</time>
        <span :class="`level-${item.level}`">{{ item.level.toUpperCase() }}</span>
        <span>{{ item.category }}</span>
        <span>{{ item.message }}</span>
      </div>
      <p v-if="!logs.length">运行日志将在这里统一显示。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { NButton, NTag } from 'naive-ui';
import type { AdaptiveRuntimeStatus, RuntimeLogEntry } from '../../types';

const props = defineProps<{ status: AdaptiveRuntimeStatus | null; logs: RuntimeLogEntry[] }>();
defineEmits<{ start: []; stop: []; diagnostics: []; 'start-simulator': []; 'stop-simulator': [] }>();
const inputRows = computed(() => props.status?.inputs || []);
function format(value: number | null | undefined) {
  return value == null ? '—' : value.toFixed(2);
}
</script>

<style scoped>
.runtime-console { padding: 18px; }
.runtime-header, .runtime-actions, .log-header { display: flex; align-items: center; }
.runtime-header, .log-header { justify-content: space-between; gap: 16px; }
.runtime-header h2, .runtime-card h3, .log-header h3 { margin: 0; }
.runtime-header p { margin: 4px 0 0; color: #555; }
.runtime-actions { gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.runtime-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 16px 0; }
.runtime-card { min-height: 130px; border: 1px solid #111; padding: 12px; display: flex; flex-direction: column; gap: 7px; }
.runtime-card strong { font-size: 22px; }
.prompt { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: #555; }
.warning, .level-error { color: #c7352b; }
.level-warning { color: #ad6a00; }
.level-info { color: #006f5b; }
.input-row { display: grid; grid-template-columns: minmax(110px, 1fr) auto 52px 54px; align-items: center; gap: 6px; font-size: 12px; }
.log-header { margin-top: 8px; }
.log-stream { margin-top: 8px; height: 210px; overflow: auto; border: 1px solid #111; background: #f8f8f5; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.log-row { display: grid; grid-template-columns: 75px 65px 90px 1fr; gap: 8px; padding: 5px 8px; border-bottom: 1px solid #ddd; }
.log-stream p { padding: 8px; }
@media (max-width: 1180px) { .runtime-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 680px) { .runtime-header, .log-header { align-items: flex-start; flex-direction: column; } .runtime-grid { grid-template-columns: 1fr; } }
</style>
