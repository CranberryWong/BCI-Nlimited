<template>
  <section class="monitor surface">
    <aside class="status">
      <h3>Emotion Monitor</h3>
      <p class="monitor-intro">实时展示情绪信号、输入状态与模型置信度。</p>
      <div class="emotion-summary">
        <div class="metric"><span>Valence</span><strong>{{ latest?.valence_class ?? '--' }}</strong></div>
        <div class="metric"><span>Arousal</span><strong>{{ latest?.arousal_class ?? '--' }}</strong></div>
        <div class="metric"><span>Current Emotion</span><strong>{{ label }}</strong></div>
      </div>
      <div class="status-details">
        <div><span>Input Source</span><strong>{{ latest?.source ?? status.latest_source ?? 'waiting' }}</strong></div>
        <div><span>Model</span><strong>{{ status.model_status ?? 'loading' }}</strong></div>
        <div><span>OSC Input</span><strong>{{ status.osc_input ?? '--' }}</strong></div>
        <div><span>Confidence</span><strong>{{ confidence }}</strong></div>
      </div>
      <div class="control-grid">
        <n-button type="primary" :disabled="simulatorRunning" @click="$emit('start-simulator')">Start Simulator</n-button>
        <n-button @click="$emit('stop-simulator')">Stop</n-button>
        <n-button :disabled="status.model_available === false" @click="$emit('start-model')">Start Model</n-button>
        <n-button @click="$emit('stop-model')">Stop Model</n-button>
      </div>
    </aside>
    <div class="chart-wrap">
      <div ref="chartEl" class="chart"></div>
    </div>
  </section>
</template>

<script setup lang="ts">
import * as echarts from 'echarts';
import { NButton } from 'naive-ui';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { EmotionState } from '../../types';

const props = defineProps<{ latest: EmotionState | null; history: EmotionState[]; status: Record<string, unknown> }>();
defineEmits(['start-simulator', 'stop-simulator', 'start-model', 'stop-model']);

const label = computed(() => props.latest?.label ?? 'waiting');
const confidence = computed(() => (props.latest ? `${Math.round(props.latest.confidence * 100)}%` : '--'));
const simulatorRunning = computed(() => props.status.simulator_running === true);
const chartEl = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;

function render() {
  if (!chart) return;
  const times = props.history.map((item) => new Date(item.timestamp * 1000).toLocaleTimeString());
  chart.setOption({
    animationDuration: 250,
    tooltip: { trigger: 'axis' },
    legend: { data: ['Valence', 'Arousal', 'Prob0', 'Prob1'] },
    grid: { left: 52, right: 52, top: 46, bottom: 76 },
    xAxis: { type: 'category', data: times, name: '时间' },
    yAxis: [
      { type: 'value', min: 1, max: 9, name: 'Valence' },
      { type: 'value', min: 0, max: 1, name: 'Probability', position: 'right' },
    ],
    dataZoom: [{ type: 'slider', bottom: 20 }, { type: 'inside' }],
    series: [
      { name: 'Valence', type: 'line', smooth: true, showSymbol: false, data: props.history.map((item) => item.valence_class), lineStyle: { color: '#2796dd', width: 2 } },
      { name: 'Arousal', type: 'line', smooth: true, showSymbol: false, data: props.history.map((item) => item.arousal_class), lineStyle: { color: '#ec567d', width: 2 } },
      { name: 'Prob0', type: 'line', yAxisIndex: 1, showSymbol: false, data: props.history.map((item) => item.valence_prob), lineStyle: { color: '#2d8a5b', type: 'dashed' } },
      { name: 'Prob1', type: 'line', yAxisIndex: 1, showSymbol: false, data: props.history.map((item) => item.arousal_prob), lineStyle: { color: '#bf6a00', type: 'dashed' } },
    ],
  });
}

function resize() {
  chart?.resize();
}

onMounted(() => {
  chart = echarts.init(chartEl.value!);
  render();
  window.addEventListener('resize', resize);
});
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize);
  chart?.dispose();
});
watch(() => props.history.length, render);
</script>

<style scoped>
.monitor {
  display: grid;
  grid-template-columns: minmax(250px, 360px) minmax(0, 1fr);
  min-height: 420px;
  padding: 24px;
  gap: 22px;
}

h3 {
  margin: 0;
}

.monitor-intro {
  margin: -8px 0 0;
  color: #5a6773;
  font-size: 13px;
}

.status {
  display: grid;
  align-content: start;
  gap: 14px;
}

.metric {
  display: grid;
  gap: 4px;
}

.emotion-summary,
.status-details {
  display: grid;
  border: 1px solid #000;
  background: #fff;
}

.emotion-summary {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.emotion-summary .metric {
  padding: 12px;
}

.emotion-summary .metric + .metric {
  border-left: 1px solid #000;
}

.metric span,
.status-details span {
  color: #5a6773;
  font-size: 12px;
}

.status-details {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.status-details > div {
  display: grid;
  gap: 4px;
  padding: 12px;
}

.status-details > div:nth-child(even) {
  border-left: 1px solid #000;
}

.status-details > div:nth-child(n + 3) {
  border-top: 1px solid #000;
}

.chart-wrap {
  min-width: 0;
  padding-top: 34px;
}

.chart {
  height: 360px;
}
.control-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.control-grid :deep(.n-button) {
  width: 100%;
  min-height: 36px;
}

@media (max-width: 900px) {
  .monitor {
    grid-template-columns: 1fr;
  }
  .emotion-summary {
    grid-template-columns: 1fr;
  }
  .emotion-summary .metric + .metric {
    border-top: 1px solid #000;
    border-left: 0;
  }
}
</style>
