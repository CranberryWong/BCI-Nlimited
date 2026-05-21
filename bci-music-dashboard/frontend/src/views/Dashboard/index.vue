<template>
  <main>
    <header class="topbar">
      <div>
        <h1>BCI Music Dashboard</h1>
        <p>Emotion state, music tracks, realtime outputs.</p>
      </div>
      <n-button @click="configOpen = true">
        <template #icon><n-icon><SlidersHorizontal /></n-icon></template>
        Music Config
      </n-button>
    </header>
    <EmotionMonitor
      :latest="emotion.latest"
      :history="emotion.history"
      :status="emotion.status"
      @start-simulator="run(emotion.startSimulator)"
      @stop-simulator="run(emotion.stopSimulator)"
      @start-model="run(emotion.startModel)"
      @stop-model="run(emotion.stopModel)"
    />
    <section class="lower">
      <TrackList :tracks="tracks.tracks" @edit="selected = $event" @toggle="run(() => tracks.patchTrack($event))" @duplicate="run(() => tracks.duplicate($event))" @remove="run(() => tracks.remove($event))" @add="run(() => tracks.add($event))" />
      <OutputPanel :tracks="tracks.tracks" :midi="outputs.midi" @test="run(() => outputs.test($event))" />
      <SessionRecorder />
    </section>
    <section class="surface events">
      <h3>Music Events</h3>
      <n-data-table :columns="eventColumns" :data="emotion.events" size="small" />
    </section>
    <TrackEditor :track="selected" :config="tracks.config" @close="selected = null" @save="saveTrack" @reset="resetTrack" />
    <MusicConfigDrawer v-model:show="configOpen" :config="tracks.config" @apply="applyConfig" @reset="run(tracks.resetConfig)" @loaded="loadedConfig" />
  </main>
</template>

<script setup lang="ts">
import { SlidersHorizontal } from 'lucide-vue-next';
import { NButton, NDataTable, NIcon, useMessage, type DataTableColumns } from 'naive-ui';
import { onMounted, ref } from 'vue';
import type { MusicConfig, MusicEvent, TrackConfig } from '../../types';
import { useEmotionStore } from '../../stores/emotion';
import { useOutputsStore } from '../../stores/outputs';
import { useTracksStore } from '../../stores/tracks';
import EmotionMonitor from './EmotionMonitor.vue';
import MusicConfigDrawer from './MusicConfigDrawer.vue';
import OutputPanel from './OutputPanel.vue';
import SessionRecorder from './SessionRecorder.vue';
import TrackEditor from './TrackEditor.vue';
import TrackList from './TrackList.vue';

const emotion = useEmotionStore();
const tracks = useTracksStore();
const outputs = useOutputsStore();
const message = useMessage();
const selected = ref<TrackConfig | null>(null);
const configOpen = ref(false);
const eventColumns: DataTableColumns<MusicEvent> = [
  { title: 'Time', key: 'timestamp', render: (row) => new Date(row.timestamp * 1000).toLocaleTimeString() },
  { title: 'Track', key: 'track_id' },
  { title: 'Type', key: 'type' },
  { title: 'Pitch', key: 'pitch' },
  { title: 'Velocity', key: 'velocity' },
];
async function run(action: () => Promise<unknown>) {
  try {
    await action();
  } catch (error) {
    message.error(error instanceof Error ? error.message : 'Request failed');
  }
}
async function saveTrack(track: TrackConfig) {
  await run(() => tracks.patchTrack(track));
  selected.value = null;
}
async function resetTrack(id: string) {
  await run(() => tracks.resetTrack(id));
  selected.value = null;
}
async function applyConfig(config: MusicConfig) {
  await run(() => tracks.applyConfig(config));
}
function loadedConfig(config: MusicConfig) {
  tracks.config = config;
  tracks.tracks = config.default_tracks;
}
onMounted(async () => {
  await Promise.all([emotion.init(), tracks.loadConfig(), outputs.loadMidi()]);
});
</script>

<style scoped>
main {
  display: grid;
  gap: 16px;
  min-height: 100vh;
  padding: 20px;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
h1, h3, p {
  margin: 0;
}
p {
  color: #586775;
}
.lower {
  display: grid;
  grid-template-columns: minmax(360px, 1.35fr) minmax(270px, 0.8fr) minmax(360px, 1fr);
  gap: 16px;
  align-items: start;
}
.events {
  padding: 18px;
}
.events h3 {
  margin-bottom: 12px;
}
@media (max-width: 1180px) {
  .lower {
    grid-template-columns: 1fr;
  }
}
</style>
