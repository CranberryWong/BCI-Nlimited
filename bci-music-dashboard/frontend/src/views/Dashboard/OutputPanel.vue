<template>
  <section class="surface panel">
    <header>
      <h3>Outputs</h3>
      <n-tag :type="midi.mode === 'mock' ? 'warning' : 'success'">MIDI {{ midi.mode }}</n-tag>
    </header>
    <p>{{ outputSummary }}</p>
    <div class="toolbar-gap">
      <n-select v-model:value="selected" :options="options" placeholder="Select track" />
      <n-button :disabled="!selected" type="primary" @click="$emit('test', selected)">Test Output</n-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { NButton, NSelect, NTag } from 'naive-ui';
import { computed, ref, watch } from 'vue';
import type { TrackConfig } from '../../types';

const props = defineProps<{ tracks: TrackConfig[]; midi: { mode: string; ports: string[]; detail: string } }>();
defineEmits(['test']);
const selected = ref<string | null>(null);
const options = computed(() => props.tracks.map((track) => ({ label: track.name, value: track.id })));
const outputSummary = computed(() => {
  if (props.midi.mode === 'rtmidi') {
    return props.midi.ports.length
      ? `已检测到 ${props.midi.ports.length} 个 MIDI 输出端口。`
      : 'MIDI 后端可用，当前未列出输出端口。';
  }
  return props.midi.detail || 'OSC 音轨会发送到各自配置的目标地址。';
});
watch(options, (items) => {
  if (!selected.value && items[0]) selected.value = items[0].value;
}, { immediate: true });
</script>

<style scoped>
.panel {
  height: 100%;
  padding: 18px;
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h3, p {
  margin: 0 0 12px;
}
.n-select {
  min-width: 220px;
}
</style>
