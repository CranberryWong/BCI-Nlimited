<template>
  <section class="monitor surface">
    <aside class="status">
      <h2>情绪监测界面</h2>
      <div class="metric"><span>Valence</span><strong>{{ latest?.valence_class ?? '--' }}</strong></div>
      <div class="metric"><span>Arousal</span><strong>{{ latest?.arousal_class ?? '--' }}</strong></div>
      <div class="emotion">{{ label }}</div>
      <n-descriptions :column="1" size="small" label-placement="left">
        <n-descriptions-item label="输入源">{{ latest?.source ?? status.latest_source ?? 'waiting' }}</n-descriptions-item>
        <n-descriptions-item label="模型">{{ status.model_status ?? 'loading' }}</n-descriptions-item>
        <n-descriptions-item label="输入 OSC">{{ status.osc_input ?? '--' }}</n-descriptions-item>
        <n-descriptions-item label="置信度">{{ confidence }}</n-descriptions-item>
      </n-descriptions>
      <div class="toolbar-gap">
        <n-button type="primary" @click="$emit('start-simulator')">Start Simulator</n-button>
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
import { NButton, NDescriptions, NDescriptionsItem } from 'naive-ui';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { EmotionState } from '../../types';

const props = defineProps<{ latest: EmotionState | null; history: EmotionState[]; status: Record<string, unknown> }>();
defineEmits(['start-simulator', 'stop-simulator', 'start-model', 'stop-model']);

const zh: Record<string, string> = { joy: '高兴', calm: '平静', neutral: '中性', tense: '紧张', sad: '悲伤' };
const label = computed(() => `当前情绪: ${props.latest ? zh[props.latest.label] : '等待数据'}`);
const confidence = computed(() => (props.latest ? `${Math.round(props.latest.confidence * 100)}%` : '--'));
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

h2 {
  margin: 0 0 18px;
  text-align: center;
  font-size: 30px;
}

.status {
  display: grid;
  align-content: start;
  gap: 14px;
}

.metric {
  display: flex;
  justify-content: space-between;
  font-size: 24px;
}

.metric strong {
  min-width: 48px;
  text-align: right;
}

.emotion {
  border-radius: 8px;
  background: #dff0dd;
  padding: 20px;
  text-align: center;
  font-weight: 700;
  font-size: 25px;
}

.chart-wrap {
  min-width: 0;
  padding-top: 34px;
}

.chart {
  height: 360px;
}

@media (max-width: 900px) {
  .monitor {
    grid-template-columns: 1fr;
  }
  h2 {
    font-size: 26px;
  }
}
</style>
