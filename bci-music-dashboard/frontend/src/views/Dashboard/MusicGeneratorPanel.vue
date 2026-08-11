<template>
  <section class="surface generator">
    <header>
      <div>
        <h3>Portrait Music Generator</h3>
        <p>等待稳定 BCI 情绪后开始演出；情绪变化只在乐句边界进入新段落。</p>
      </div>
      <n-tag :type="status?.running ? 'success' : 'default'">
        {{ status?.running ? 'running' : 'stopped' }}
      </n-tag>
    </header>
    <div class="metrics">
      <div><span>初始情绪</span><strong>{{ initialReadiness }}</strong></div>
      <div><span>4秒 / 16秒情绪</span><strong>{{ status?.fast_window_emotion ?? 'neutral' }} / {{ status?.slow_window_emotion ?? 'neutral' }}</strong></div>
      <div><span>当前Portrait</span><strong>{{ status?.current_portrait ?? status?.current_emotion ?? 'neutral' }}</strong></div>
      <div><span>当前段落资产</span><strong>{{ portraitLabel }}</strong></div>
      <div><span>当前和弦</span><strong>{{ status?.current_harmony || '--' }}</strong></div>
      <div><span>本段和声</span><strong>{{ harmonyProgression }}</strong></div>
      <div><span>自动和声音</span><strong>{{ status?.harmony_note_count ?? 0 }}</strong></div>
      <div><span>琶音音数</span><strong>{{ status?.arpeggio_note_count ?? 0 }}</strong></div>
      <div><span>Bass / Drum / Cymbal</span><strong>{{ status?.bass_note_count ?? 0 }} / {{ status?.drum_note_count ?? 0 }} / {{ status?.cymbal_note_count ?? 0 }}</strong></div>
      <div><span>基准 / 实际 / 目标 BPM</span><strong>{{ status?.base_bpm ?? '--' }} / {{ status?.effective_bpm ?? '--' }} / {{ status?.next_target_bpm ?? '--' }}</strong></div>
      <div><span>Notochord Assist</span><strong>{{ notochordSummary }}</strong></div>
      <div><span>下一段</span><strong>{{ nextPortrait }}</strong></div>
      <div><span>木琴同键保护</span><strong>{{ xylophoneGuard }}</strong></div>
      <div><span>木琴实际声部</span><strong>{{ status?.actual_max_voices ?? 1 }}</strong></div>
      <div><span>慢窗口样本</span><strong>{{ status?.window_samples ?? 0 }} / {{ status?.required_initial_samples ?? 4 }}</strong></div>
      <div><span>当前 / 候选情绪</span><strong>{{ status?.current_emotion ?? 'neutral' }} / {{ status?.candidate_emotion ?? 'neutral' }}</strong></div>
      <div><span>平滑情绪</span><strong>{{ smoothedEmotion }}</strong></div>
      <div><span>BPM</span><strong>{{ status?.bpm ?? '--' }}</strong></div>
      <div><span>片段剩余</span><strong>{{ remaining }}</strong></div>
      <div><span>下一段缓冲</span><strong>{{ status?.next_segment_ready ? 'ready' : 'pending' }}</strong></div>
      <div v-if="presetsTesting"><span>Experiment / 原始Preset</span><strong>{{ presetsTesting.type }} · {{ presetsTesting.raw_preset_id || '等待稳定情绪' }}</strong></div>
      <div v-if="presetsTesting"><span>窗口 / 原始BPM</span><strong>{{ presetsTesting.window_start_beat }} · {{ presetsTesting.window_bars }} bars / {{ presetsTesting.raw_bpm ?? '--' }}</strong></div>
      <div v-if="presetsTesting"><span>实验BPM</span><strong>{{ presetsTesting.current_bpm }}</strong></div>
      <div v-if="presetsTesting"><span>Drum/Cymbal Rule / Notochord</span><strong>{{ presetsTesting.rule_percussion_count }} / {{ presetsTesting.notochord_percussion_count }}</strong></div>
    </div>
    <n-alert v-if="status?.generation_error" type="warning" :show-icon="false">
      {{ status.generation_error }}
    </n-alert>
    <div class="actions">
      <n-switch
        :value="status?.portrait_harmony_enabled ?? false"
        :disabled="!status"
        @update:value="$emit('updatePortraitHarmony', $event)"
      >
        <template #checked>木琴和声</template>
        <template #unchecked>木琴和声</template>
      </n-switch>
      <n-switch
        :value="status?.portrait_harmony_arpeggio_enabled ?? false"
        :disabled="!status || !(status?.portrait_harmony_enabled ?? false)"
        @update:value="$emit('updatePortraitHarmonyArpeggio', $event)"
      >
        <template #checked>琶音</template>
        <template #unchecked>琶音</template>
      </n-switch>
      <n-button type="primary" :disabled="status?.running || Boolean(presetsTesting?.running) || Boolean(notoTesting?.running)" @click="$emit('start')">Start Generator</n-button>
      <n-button secondary :disabled="status?.running || Boolean(presetsTesting?.running) || Boolean(notoTesting?.running)" @click="$emit('startPresetsTesting')">Presets Testing</n-button>
      <n-button v-if="presetsTesting?.running" @click="$emit('stopPresetsTesting')">Stop Presets Testing</n-button>
      <n-button :disabled="!status?.running" @click="$emit('stop')">Stop Generator</n-button>
    </div>
    <section class="noto-testing">
      <div>
        <h4>Sound-first Notochord Ensemble</h4>
        <p>Notochord 从第一颗音开始连续写满所有启用声部；当前情绪只轻微影响速度与力度，不限制旋律、和声或音阶。</p>
      </div>
      <n-tag :type="notoTesting?.running ? 'success' : notoTesting?.phase === 'error' ? 'error' : 'default'">
        {{ notoTesting?.phase ?? 'stopped' }}
      </n-tag>
      <div class="noto-metrics">
        <span>节拍参考：{{ notoTesting?.initial_asset_title || '等待稳定情绪' }}</span>
        <span>当前情绪（轻约束）：{{ notoTesting?.current_emotion ?? 'neutral' }} · {{ notoTesting?.current_bpm ?? '--' }} BPM</span>
        <span>段落：{{ notoTesting?.segment_index ?? 0 }} · {{ notoTesting?.window_bars ?? 4 }} bars · {{ notoTesting?.current_bpm ?? '--' }} BPM</span>
        <span>Notochord events：{{ notoTesting?.notochord_event_count ?? 0 }}</span>
      </div>
      <n-alert v-if="notoTesting?.generation_error" type="error" :show-icon="false">{{ notoTesting.generation_error }}</n-alert>
      <div class="actions">
        <n-button type="warning" :disabled="Boolean(status?.running) || Boolean(presetsTesting?.running) || Boolean(notoTesting?.running)" @click="$emit('startNotoTesting')">Start Sound-first Ensemble</n-button>
        <n-button v-if="notoTesting?.running" @click="$emit('stopNotoTesting')">Stop Sound-first Ensemble</n-button>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { NAlert, NButton, NSwitch, NTag } from 'naive-ui';
import { computed } from 'vue';
import type { MusicGeneratorStatus, NotoTestingStatus, PresetsTestingStatus } from '../../types';

const props = defineProps<{ status: MusicGeneratorStatus | null; presetsTesting?: PresetsTestingStatus | null; notoTesting?: NotoTestingStatus | null }>();
const emit = defineEmits<{
  start: [];
  stop: [];
  startPresetsTesting: [];
  stopPresetsTesting: [];
  startNotoTesting: [];
  stopNotoTesting: [];
  updatePortraitHarmony: [enabled: boolean];
  updatePortraitHarmonyArpeggio: [enabled: boolean];
}>();
const remaining = computed(() => (
  props.status?.remaining_seconds == null ? '--' : `${props.status.remaining_seconds.toFixed(1)}s`
));
const smoothedEmotion = computed(() => {
  const emotion = props.status?.smoothed_emotion;
  if (!emotion) return '--';
  return `${emotion.label} · V${emotion.valence_norm.toFixed(2)} A${emotion.arousal_norm.toFixed(2)} C${emotion.confidence.toFixed(2)}`;
});
const initialReadiness = computed(() => (
  props.status?.initial_emotion_ready
    ? props.status.active_portrait_emotion ?? 'ready'
    : `等待 ${props.status?.window_samples ?? 0}/${props.status?.required_initial_samples ?? 4}`
));
const portraitLabel = computed(() => {
  const asset = props.status?.current_portrait_asset_title ?? props.status?.current_portrait_asset_id;
  if (!asset) return '等待首个乐句';
  return `${asset} · ${props.status?.portrait_role || 'loop'}`;
});
const xylophoneGuard = computed(() => (
  `${props.status?.xylophone_same_key_minimum_interval_seconds ?? 1}s · blocked ${props.status?.xylophone_suppressed_count ?? 0}`
));
const nextPortrait = computed(() => (
  props.status?.pending_portrait_emotion
    ? `${props.status.pending_portrait_emotion} · loop`
    : props.status?.next_portrait_role ?? 'loop'
));
const harmonyProgression = computed(() => {
  if (!props.status?.portrait_harmony_enabled) return 'off';
  const progression = props.status?.harmony_progression ?? [];
  return progression.length ? progression.join(' - ') : '下一乐句生效';
});
const notochordSummary = computed(() => {
  const tracks = Object.values(props.status?.notochord_tracks ?? {});
  const active = tracks.filter((track) => track.enabled);
  if (!active.length) return 'off';
  const available = active.filter((track) => track.available).length;
  const changed = Object.values(props.status?.notochord_track_counts ?? {}).reduce((sum, count) => sum + count, 0);
  return `${available}/${active.length} ready · ${changed} changed`;
});
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
.noto-testing {
  display: grid;
  gap: 10px;
  border: 1px dashed #000;
  padding: 14px;
}
.noto-testing > div:first-child {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
h4 { margin: 0; }
.noto-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 14px;
  font-size: 12px;
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
