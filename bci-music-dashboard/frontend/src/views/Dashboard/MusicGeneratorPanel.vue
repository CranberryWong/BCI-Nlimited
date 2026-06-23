<template>
  <section class="surface generator">
    <header>
      <div>
        <h3>Theme-Driven Music Generator</h3>
        <p>EEG 连续控制演奏细节，情绪结构只在八小节乐句边界变化。</p>
      </div>
      <n-tag :type="status?.running ? 'success' : 'default'">
        {{ status?.running ? 'running' : 'stopped' }}
      </n-tag>
    </header>
    <div class="theme-controls">
      <n-select
        :value="status?.theme_id"
        :options="themeOptions"
        :disabled="status?.running || !themeOptions.length"
        placeholder="选择主题"
        @update:value="$emit('select-theme', $event)"
      />
      <n-button :disabled="status?.running || !themeOptions.length" @click="$emit('random-theme')">
        随机选曲
      </n-button>
      <n-select
        class="mode-select"
        :value="status?.system_mode ?? 'ENGAGING'"
        :options="modeOptions"
        @update:value="setMode"
      />
    </div>
    <div class="metrics">
      <div><span>闭环模式</span><strong>{{ status?.system_mode ?? 'ENGAGING' }}</strong></div>
      <div><span>ENGAGING阶段</span><strong>{{ stageLabel }}</strong></div>
      <div><span>阶段进度</span><strong>{{ stageProgress }}</strong></div>
      <div><span>目标接近度</span><strong>{{ targetProgress }}</strong></div>
      <div><span>4秒/16秒情绪</span><strong>{{ status?.fast_window_emotion ?? 'neutral' }} / {{ status?.slow_window_emotion ?? 'neutral' }}</strong></div>
      <div><span>主旋律来源</span><strong>{{ status?.segment_source ?? status?.composition_mode ?? 'hybrid' }}</strong></div>
      <div><span>当前Portrait</span><strong>{{ status?.current_portrait ?? status?.current_emotion ?? 'neutral' }}</strong></div>
      <div><span>当前Motif</span><strong>{{ motifLabel }}</strong></div>
      <div><span>主题</span><strong>{{ status?.theme_title ?? status?.theme_id ?? '未选择' }}</strong></div>
      <div><span>曲式阶段</span><strong>{{ sectionLabel }}</strong></div>
      <div><span>乐句进度</span><strong>{{ phraseProgress }}</strong></div>
      <div><span>主题辨识度</span><strong>{{ similarity }}</strong></div>
      <div><span>木琴实际声部</span><strong>{{ status?.actual_max_voices ?? 1 }}</strong></div>
      <div><span>规则和声音</span><strong>{{ status?.harmony_note_count ?? 0 }}</strong></div>
      <div><span>木琴琶音</span><strong>{{ status?.arpeggio_note_count ?? 0 }}</strong></div>
      <div><span>Notochord修饰</span><strong>{{ status?.notochord_modified_count ?? 0 }}</strong></div>
      <div><span>作曲模式</span><strong>{{ status?.composition_mode ?? 'hybrid' }}</strong></div>
      <div><span>装饰模型</span><strong>{{ status?.model_detail ?? 'loading' }}</strong></div>
      <div><span>窗口</span><strong>{{ status?.window_samples ?? 0 }}/{{ Math.round(status?.window_seconds ?? 16) }} samples</strong></div>
      <div><span>快窗口</span><strong>{{ status?.fast_window_samples ?? 0 }}/{{ Math.round(status?.fast_window_seconds ?? 4) }} samples</strong></div>
      <div><span>当前/候选情绪</span><strong>{{ status?.current_emotion ?? 'neutral' }} / {{ status?.candidate_emotion ?? 'neutral' }}</strong></div>
      <div><span>平滑情绪</span><strong>{{ smoothedEmotion }}</strong></div>
      <div><span>BPM</span><strong>{{ status?.bpm ?? '--' }}</strong></div>
      <div><span>参数Tempo</span><strong>{{ musicParams?.tempo ?? '--' }}</strong></div>
      <div><span>Density / Velocity</span><strong>{{ paramPair('density', 'velocity') }}</strong></div>
      <div><span>Register</span><strong>{{ musicParams?.register ?? '--' }}</strong></div>
      <div><span>Brightness / Tension</span><strong>{{ paramPair('brightness', 'tension') }}</strong></div>
      <div><span>Reverb / Delay</span><strong>{{ paramPair('reverb', 'delay') }}</strong></div>
      <div><span>Instruments</span><strong>{{ instruments }}</strong></div>
      <div><span>片段剩余</span><strong>{{ remaining }}</strong></div>
      <div><span>下一段缓冲</span><strong>{{ status?.next_segment_ready ? 'ready' : 'pending' }}</strong></div>
      <div><span>情绪转场</span><strong>{{ transitionLabel }}</strong></div>
      <div><span>规则回退</span><strong>{{ status?.fallback_count ?? 0 }}</strong></div>
    </div>
    <div class="settings">
      <label>
        <span>主题辨识度 {{ Math.round(recognition * 100) }}%</span>
        <n-slider v-model:value="recognition" :min="0.4" :max="1" :step="0.05" />
      </label>
      <label>
        <span>生成自由度 {{ Math.round(freedom * 100) }}%</span>
        <n-slider v-model:value="freedom" :min="0" :max="0.8" :step="0.05" />
      </label>
      <label>
        <span>主旋律来源</span>
        <n-select v-model:value="compositionMode" :options="compositionOptions" />
      </label>
      <n-button @click="applySettings">应用到后续乐句</n-button>
    </div>
    <n-alert v-if="status?.generation_error" type="warning" :show-icon="false">
      {{ status.generation_error }}
    </n-alert>
    <div class="actions">
      <n-button type="primary" :disabled="status?.running" @click="$emit('start')">Start Generator</n-button>
      <n-button :disabled="!status?.running" @click="$emit('stop')">Stop Generator</n-button>
      <n-button @click="$emit('reload')">Reload Music Model</n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { NAlert, NButton, NSelect, NSlider, NTag } from 'naive-ui';
import { computed, ref, watch } from 'vue';
import type { CompositionMode, MusicGeneratorStatus, MusicParams, SystemMode } from '../../types';

const props = defineProps<{ status: MusicGeneratorStatus | null }>();
const emit = defineEmits<{
  start: [];
  stop: [];
  reload: [];
  'select-theme': [themeId: string];
  'random-theme': [];
  'update-settings': [settings: { theme_recognition: number; generation_freedom: number; composition_mode?: CompositionMode }];
  'set-mode': [mode: SystemMode];
}>();
const recognition = ref(0.65);
const freedom = ref(0.35);
const compositionMode = ref<CompositionMode>('hybrid');
const modeOptions = [
  { label: 'MIRROR', value: 'MIRROR' },
  { label: 'ENGAGING', value: 'ENGAGING' },
];
const compositionOptions = [
  { label: 'Hybrid', value: 'hybrid' },
  { label: 'Theme only', value: 'theme' },
  { label: 'Motif only', value: 'motif' },
];
watch(
  () => props.status,
  (status) => {
    if (!status) return;
    recognition.value = status.theme_recognition;
    freedom.value = status.generation_freedom;
    compositionMode.value = status.composition_mode === 'anchored'
      ? 'theme'
      : status.composition_mode === 'generative'
        ? 'motif'
        : status.composition_mode;
  },
  { immediate: true },
);
const remaining = computed(() => (
  props.status?.remaining_seconds == null ? '--' : `${props.status.remaining_seconds.toFixed(1)}s`
));
const themeOptions = computed(() => (
  props.status?.available_themes.map((theme) => ({
    label: `${theme.title} · ${theme.home_key} ${theme.mode}`,
    value: theme.id,
  })) ?? []
));
const phraseProgress = computed(() => {
  if (!props.status) return '--';
  return `${Math.min(props.status.phrase_index + 1, props.status.total_phrases)}/${props.status.total_phrases}`;
});
const sectionLabel = computed(() => props.status?.form_section ?? '等待开始');
const similarity = computed(() => (
  props.status?.theme_similarity == null
    ? '--'
    : `${Math.round(props.status.theme_similarity * 100)}%`
));
const musicParams = computed<MusicParams | null>(() => props.status?.music_params ?? null);
const stageLabel = computed(() => (
  props.status?.system_mode === 'MIRROR'
    ? 'Mirroring current state'
    : props.status?.engaging_stage ?? 'Resonance'
));
const stageProgress = computed(() => (
  props.status?.system_mode === 'MIRROR'
    ? '--'
    : `${Math.round((props.status?.stage_progress ?? 0) * 100)}%`
));
const targetProgress = computed(() => `${Math.round((props.status?.target_state_progress ?? 0) * 100)}%`);
const smoothedEmotion = computed(() => {
  const emotion = props.status?.smoothed_emotion;
  if (!emotion) return '--';
  return `${emotion.label} · V${emotion.valence_norm.toFixed(2)} A${emotion.arousal_norm.toFixed(2)} C${emotion.confidence.toFixed(2)}`;
});
const instruments = computed(() => {
  const entries = Object.entries(musicParams.value?.instruments ?? {})
    .filter(([, value]) => value > 0.01)
    .sort((a, b) => b[1] - a[1]);
  if (!entries.length) return '--';
  return entries.map(([key, value]) => `${key} ${Math.round(value * 100)}%`).join(' · ');
});
const motifLabel = computed(() => {
  if (!props.status?.current_motif_id) return '无 approved motif';
  return `${props.status.current_motif_title ?? props.status.current_motif_id} · ${props.status.motif_approved ? 'approved' : 'draft'}`;
});
const transitionLabel = computed(() => {
  if (!props.status?.transition_strategy) return 'continue';
  const preparing = props.status.transition_preparing ? 'preparing' : 'ready';
  return `${props.status.transition_strategy} · ${preparing} · ${Math.round((props.status.transition_progress ?? 0) * 100)}%`;
});
function paramPair(first: keyof MusicParams, second: keyof MusicParams) {
  const params = musicParams.value;
  if (!params) return '--';
  const a = params[first];
  const b = params[second];
  return `${formatParam(a)} / ${formatParam(b)}`;
}
function formatParam(value: MusicParams[keyof MusicParams]) {
  return typeof value === 'number' ? value.toFixed(2) : String(value);
}
function applySettings() {
  emit('update-settings', {
    theme_recognition: recognition.value,
    generation_freedom: freedom.value,
    composition_mode: compositionMode.value,
  });
}
function setMode(value: string | number) {
  emit('set-mode', value === 'MIRROR' ? 'MIRROR' : 'ENGAGING');
}
</script>

<style scoped>
.generator {
  display: grid;
  gap: 14px;
  padding: 18px;
}
header,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
h3,
p {
  margin: 0;
}
p {
  margin-top: 4px;
  font-size: 13px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.theme-controls,
.settings {
  display: flex;
  align-items: center;
  gap: 12px;
}
.theme-controls :deep(.n-select) {
  max-width: 420px;
  flex: 1;
}
.theme-controls :deep(.mode-select) {
  max-width: 160px;
  flex: 0 0 160px;
}
.settings label {
  display: grid;
  gap: 6px;
  min-width: 220px;
  flex: 1;
}
.settings span {
  font-size: 12px;
}
.metrics div {
  display: grid;
  gap: 4px;
  border: 1px solid #000;
  padding: 10px;
}
.metrics span {
  font-size: 12px;
}
@media (max-width: 900px) {
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  header,
  .actions {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .settings {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
