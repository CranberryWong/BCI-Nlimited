<template>
  <section class="surface panel">
    <header>
      <h3>Session Recorder</h3>
      <n-tag :type="active ? 'success' : 'default'">{{ active ? active : 'idle' }}</n-tag>
    </header>
    <div class="toolbar-gap">
      <n-button type="primary" :disabled="Boolean(active)" @click="start">Start Recording</n-button>
      <n-button :disabled="!active" @click="stop">Stop Recording</n-button>
      <n-button @click="load">Refresh</n-button>
    </div>
    <p>录制期间会保存情绪、MIDI、主题、曲式、和声、变奏与模型元数据。</p>
    <div class="session-table">
      <n-data-table :columns="columns" :data="sessions" size="small" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { NButton, NDataTable, NTag, type DataTableColumns } from 'naive-ui';
import { h, onMounted, ref } from 'vue';
import { api } from '../../api/client';

type Session = { id: string; files: string[] };
const active = ref<string | null>(null);
const sessions = ref<Session[]>([]);
async function start() {
  active.value = (await api.post('/sessions/start')).data.id;
}
async function stop() {
  await api.post('/sessions/stop');
  active.value = null;
  await load();
}
async function load() {
  sessions.value = (await api.get('/sessions')).data;
}
const columns: DataTableColumns<Session> = [
  { title: 'Session', key: 'id' },
  {
    title: 'Export',
    key: 'actions',
    render: (row) => h('div', { class: 'file-actions' }, exports
      .filter((item) => row.files.includes(item.file))
      .map((item) => h(NButton, {
        size: 'small',
        tag: 'a',
        href: `/api/sessions/${row.id}/download?format=${item.format}`,
      }, { default: () => item.file }))),
  },
];
const exports = [
  { file: 'music.mid', format: 'mid' },
  { file: 'emotion.csv', format: 'csv' },
  { file: 'emotion_timeline.jsonl', format: 'emotion-jsonl' },
  { file: 'music_event_log.jsonl', format: 'music-jsonl' },
  { file: 'music_config_snapshot.yaml', format: 'config' },
  { file: 'music_segments.jsonl', format: 'segments' },
  { file: 'generator_status.json', format: 'generator-status' },
  { file: 'model_metadata.json', format: 'model-metadata' },
  { file: 'composition_metadata.json', format: 'composition-metadata' },
];
onMounted(load);
</script>

<style scoped>
.panel {
  display: grid;
  height: 100%;
  gap: 12px;
  padding: 18px;
}
header {
  display: flex;
  justify-content: space-between;
}
h3 {
  margin: 0;
}
p {
  margin: 0;
  font-size: 13px;
}
:deep(.file-actions) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.session-table {
  max-height: 240px;
  overflow: auto;
  border: 1px solid #000;
}
</style>
