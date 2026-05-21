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
    <n-data-table :columns="columns" :data="sessions" size="small" />
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
  { title: 'Files', key: 'files', render: (row) => row.files.join(', ') },
  {
    title: 'Export',
    key: 'actions',
    render: (row) => h('div', { class: 'toolbar-gap' }, ['mid', 'jsonl', 'csv'].map((format) =>
      h(NButton, { size: 'small', tag: 'a', href: `/api/sessions/${row.id}/download?format=${format}` }, { default: () => format.toUpperCase() }),
    )),
  },
];
onMounted(load);
</script>

<style scoped>
.panel {
  display: grid;
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
</style>
