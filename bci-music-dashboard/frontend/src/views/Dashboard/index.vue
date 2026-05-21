<template>
  <main>
    <header class="topbar">
      <div class="brand">
        <img src="/sign01.svg" alt="和鸣 Logo" />
        <div>
          <h1>和鸣-BCI Dashboard</h1>
          <p style="margin-top: -5px;">Powered by 雷士德神经共振技术小组 | Version {{ APP_VERSION }}</p>
        </div>
      </div>
      <div class="top-actions">
        <n-button @click="helpOpen = true">
          <template #icon><n-icon><BookOpenText /></n-icon></template>
          使用说明
        </n-button>
        <n-button @click="configOpen = true">
          <template #icon><n-icon><SlidersHorizontal /></n-icon></template>
          Music Config
        </n-button>
      </div>
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
      <header class="events-header"><h3>Music Events</h3></header>
      <div class="events-scroll">
        <n-data-table :columns="eventColumns" :data="emotion.events" size="small" />
      </div>
    </section>
    <TrackEditor :track="selected" :config="tracks.config" @close="selected = null" @save="saveTrack" @reset="resetTrack" />
    <UsageHelpDrawer v-model:show="helpOpen" />
    <MusicConfigDrawer v-model:show="configOpen" :config="tracks.config" @apply="applyConfig" @reset="run(tracks.resetConfig)" @loaded="loadedConfig" />
  </main>
</template>

<script setup lang="ts">
import { BookOpenText, SlidersHorizontal } from 'lucide-vue-next';
import { NButton, NDataTable, NIcon, useMessage, type DataTableColumns } from 'naive-ui';
import { onMounted, ref } from 'vue';
import type { MusicConfig, MusicEvent, TrackConfig } from '../../types';
import { useEmotionStore } from '../../stores/emotion';
import { useOutputsStore } from '../../stores/outputs';
import { useTracksStore } from '../../stores/tracks';
import { APP_VERSION } from '../../version';
import EmotionMonitor from './EmotionMonitor.vue';
import MusicConfigDrawer from './MusicConfigDrawer.vue';
import OutputPanel from './OutputPanel.vue';
import SessionRecorder from './SessionRecorder.vue';
import TrackEditor from './TrackEditor.vue';
import TrackList from './TrackList.vue';
import UsageHelpDrawer from './UsageHelpDrawer.vue';

const emotion = useEmotionStore();
const tracks = useTracksStore();
const outputs = useOutputsStore();
const message = useMessage();
const selected = ref<TrackConfig | null>(null);
const configOpen = ref(false);
const helpOpen = ref(false);
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
  gap: 16px;
}
h1, h3 {
  margin: 0;
}
.brand p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #111;
}
.brand,
.top-actions,
.events-header {
  display: flex;
  align-items: center;
}
.brand {
  gap: 16px;
}
.brand img {
  display: block;
  width: 34px;
  height: 40px;
}
.top-actions {
  gap: 8px;
}
.lower {
  display: grid;
  grid-template-columns: minmax(360px, 1.35fr) minmax(270px, 0.8fr) minmax(360px, 1fr);
  gap: 16px;
  align-items: stretch;
}
.lower > * {
  min-height: 320px;
}
.events {
  padding: 18px;
}
.events h3 {
  margin: 0;
}
.events-header {
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.events-scroll {
  max-height: 340px;
  overflow: auto;
  border: 1px solid #000;
}
@media (max-width: 680px) {
  .topbar,
  .events-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
@media (max-width: 1180px) {
  .lower {
    grid-template-columns: 1fr;
  }
}
</style>
