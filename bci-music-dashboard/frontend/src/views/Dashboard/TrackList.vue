<template>
  <section class="surface track-list">
    <header>
      <h3>Tracks</h3>
      <n-dropdown :options="addOptions" @select="(role) => $emit('add', role)">
        <n-button type="primary">
          <template #icon><n-icon><Plus /></n-icon></template>
          Add Track
        </n-button>
      </n-dropdown>
    </header>
    <div class="rows">
      <article v-for="track in tracks" :key="track.id" class="track-row">
        <div>
          <strong>{{ track.name }}</strong>
          <span>{{ track.role }} · {{ track.output_type.toUpperCase() }} · ch {{ track.midi_channel }}</span>
        </div>
        <n-switch :value="track.enabled" @update:value="$emit('toggle', { ...track, enabled: $event })" />
        <n-switch :value="track.compute_enabled" @update:value="$emit('toggle', { ...track, compute_enabled: $event })">
          <template #checked>Play</template>
          <template #unchecked>Hold</template>
        </n-switch>
        <div class="actions">
          <n-button quaternary circle title="Edit track" @click="$emit('edit', track)"><template #icon><n-icon><Pencil /></n-icon></template></n-button>
          <n-button quaternary circle title="Duplicate track" @click="$emit('duplicate', track.id)"><template #icon><n-icon><Copy /></n-icon></template></n-button>
          <n-button quaternary circle title="Delete track" @click="$emit('remove', track.id)"><template #icon><n-icon><Trash2 /></n-icon></template></n-button>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Copy, Pencil, Plus, Trash2 } from 'lucide-vue-next';
import { NButton, NDropdown, NIcon, NSwitch } from 'naive-ui';
import type { TrackConfig } from '../../types';

defineProps<{ tracks: TrackConfig[] }>();
defineEmits(['edit', 'toggle', 'duplicate', 'remove', 'add']);
const addOptions = [
  { label: 'Add Melody Track', key: 'melody' },
  { label: 'Add Chord Track', key: 'chord' },
  { label: 'Add Bass Track', key: 'bass' },
  { label: 'Add Drum Track', key: 'drum' },
  { label: 'Add Cymbal Track', key: 'cymbal' },
  { label: 'Add Pad Track', key: 'pad' },
];
</script>

<style scoped>
.track-list {
  padding: 18px;
}

header, .track-row {
  display: grid;
  align-items: center;
  gap: 12px;
  grid-template-columns: minmax(180px, 1fr) auto auto auto;
}

header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

h3 {
  margin: 0;
}

.rows {
  display: grid;
  gap: 8px;
}

.track-row {
  border-top: 1px solid #e4ebf0;
  padding-top: 10px;
}

.track-row strong, .track-row span {
  display: block;
}

.track-row span {
  color: #5a6773;
  font-size: 12px;
}

.actions {
  display: flex;
}
</style>
