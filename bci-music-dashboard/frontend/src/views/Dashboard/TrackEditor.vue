<template>
  <n-drawer :show="Boolean(track)" width="560" @update:show="!$event && $emit('close')">
    <n-drawer-content v-if="draft" title="Track Editor" closable>
      <n-form label-placement="top">
        <div class="two">
          <n-form-item label="Track name"><n-input v-model:value="draft.name" /></n-form-item>
          <n-form-item label="Role"><n-select v-model:value="draft.role" :options="roleOptions" /></n-form-item>
          <n-form-item label="Instrument"><n-input v-model:value="draft.instrument" /></n-form-item>
          <n-form-item label="Output"><n-select v-model:value="draft.output_type" :options="outputOptions" /></n-form-item>
          <n-form-item label="Target IP"><n-input v-model:value="draft.target_ip" /></n-form-item>
          <n-form-item label="Target port"><n-input-number v-model:value="draft.target_port" :min="1" :max="65535" /></n-form-item>
          <n-form-item label="MIDI channel"><n-input-number v-model:value="draft.midi_channel" :min="1" :max="16" /></n-form-item>
          <n-form-item label="MIDI program"><n-input-number v-model:value="draft.midi_program" :min="0" :max="127" clearable /></n-form-item>
          <n-form-item label="Root note"><n-select v-model:value="draft.root_note" :options="rootOptions" /></n-form-item>
          <n-form-item label="Scale"><n-select v-model:value="draft.scale" :options="scaleOptions" /></n-form-item>
        </div>
        <range-row label="Pitch Range" v-model="draft.pitch_range" :min="schema.pitch_range?.min ?? 0" :max="schema.pitch_range?.max ?? 127" />
        <range-row label="Velocity Range" v-model="draft.velocity_range" :min="schema.velocity_range?.min ?? 0" :max="schema.velocity_range?.max ?? 127" />
        <scalar-row label="Density" v-model="draft.density" :min="schema.density?.min ?? 0" :max="schema.density?.max ?? 1" :step="0.01" />
        <scalar-row label="Delay ms" v-model="draft.delay_ms" :min="schema.delay_ms?.min ?? 0" :max="schema.delay_ms?.max ?? 5000" :step="1" />
        <scalar-row label="Note Length ms" v-model="draft.note_length_ms" :min="schema.note_length_ms?.min ?? 20" :max="schema.note_length_ms?.max ?? 10000" :step="1" />
        <scalar-row label="Humanize" v-model="draft.humanize" :min="schema.humanize?.min ?? 0" :max="schema.humanize?.max ?? 1" :step="0.01" />
        <n-form-item label="BPM">
          <n-radio-group :value="draft.bpm === 'auto' ? 'auto' : 'manual'" @update:value="setBpmMode">
            <n-radio-button value="auto">Auto</n-radio-button>
            <n-radio-button value="manual">Manual</n-radio-button>
          </n-radio-group>
          <n-input-number v-if="draft.bpm !== 'auto'" v-model:value="manualBpm" :min="schema.bpm?.min ?? 30" :max="schema.bpm?.max ?? 220" @update:value="draft.bpm = $event ?? 96" />
        </n-form-item>
        <h4>Mapping Weights</h4>
        <scalar-row v-for="(_, key) in draft.mapping" :key="key" :label="String(key)" v-model="draft.mapping[key]" :min="schema.mapping_weight?.min ?? -1" :max="schema.mapping_weight?.max ?? 1" :step="0.01" />
        <template v-if="draft.role === 'drum'">
          <h4>Drum Notes</h4>
          <div class="two">
            <n-form-item v-for="note in drumKeys" :key="note" :label="note">
              <n-input-number :value="drumNote(note)" :min="0" :max="127" @update:value="setDrumNote(note, $event)" />
            </n-form-item>
          </div>
        </template>
        <template v-if="draft.role === 'cymbal'">
          <h4>Cymbal Trigger</h4>
          <n-form-item label="Trigger on arousal rise">
            <n-switch :value="Boolean(draft.trigger_on_arousal_rise)" @update:value="draft.trigger_on_arousal_rise = $event" />
          </n-form-item>
          <scalar-row label="Arousal Rise Threshold" :model-value="extraNumber('arousal_rise_threshold', 0.18)" :min="0" :max="1" :step="0.01" @update:model-value="draft.arousal_rise_threshold = $event" />
        </template>
      </n-form>
      <template #footer>
        <div class="toolbar-gap">
          <n-button @click="$emit('reset', draft.id)">Reset</n-button>
          <n-button type="primary" @click="$emit('save', draft)">Apply</n-button>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NInputNumber, NRadioButton, NRadioGroup, NSelect, NSlider, NSwitch } from 'naive-ui';
import { computed, defineComponent, h, ref, watch } from 'vue';
import type { MusicConfig, TrackConfig } from '../../types';

const props = defineProps<{ track: TrackConfig | null; config: MusicConfig | null }>();
defineEmits(['close', 'save', 'reset']);
const draft = ref<TrackConfig | null>(null);
const schema = computed(() => props.config?.music_parameter_schema ?? {});
const manualBpm = ref(96);
watch(() => props.track, (track) => {
  draft.value = track ? JSON.parse(JSON.stringify(track)) : null;
  manualBpm.value = typeof track?.bpm === 'number' ? track.bpm : 96;
}, { immediate: true });

function setBpmMode(mode: 'auto' | 'manual') {
  if (!draft.value) return;
  draft.value.bpm = mode === 'auto' ? 'auto' : manualBpm.value;
}
const drumKeys = ['kick', 'snare', 'closed_hat', 'open_hat', 'crash', 'ride'];
function drumMap() {
  if (!draft.value) return {};
  if (!draft.value.drum_notes || typeof draft.value.drum_notes !== 'object') draft.value.drum_notes = {};
  return draft.value.drum_notes as Record<string, number>;
}
function drumNote(key: string) {
  return drumMap()[key] ?? 36;
}
function setDrumNote(key: string, value: number | null) {
  drumMap()[key] = value ?? 0;
}
function extraNumber(key: string, fallback: number) {
  return Number(draft.value?.[key] ?? fallback);
}

const roleOptions = ['melody', 'chord', 'bass', 'drum', 'cymbal', 'pad', 'fx'].map((value) => ({ label: value, value }));
const outputOptions = ['osc', 'midi'].map((value) => ({ label: value.toUpperCase(), value }));
const rootOptions = ['auto', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].map((value) => ({ label: value, value }));
const scaleOptions = ['auto', 'major', 'minor', 'pentatonic', 'chromatic', 'dorian', 'lydian', 'phrygian'].map((value) => ({ label: value, value }));

const ScalarRow = defineComponent({
  props: { modelValue: Number, label: String, min: Number, max: Number, step: Number },
  emits: ['update:modelValue'],
  setup(componentProps, { emit }) {
    return () => h(NFormItem, { label: componentProps.label }, {
      default: () => h('div', { class: 'dual' }, [
        h(NSlider, {
          value: componentProps.modelValue,
          min: componentProps.min,
          max: componentProps.max,
          step: componentProps.step,
          'onUpdate:value': (value: number) => emit('update:modelValue', value),
        }),
        h(NInputNumber, {
          value: componentProps.modelValue,
          min: componentProps.min,
          max: componentProps.max,
          step: componentProps.step,
          'onUpdate:value': (value: number | null) => emit('update:modelValue', value ?? componentProps.min),
        }),
      ]),
    });
  },
});

const RangeRow = defineComponent({
  props: { modelValue: Array<number>, label: String, min: Number, max: Number },
  emits: ['update:modelValue'],
  setup(componentProps, { emit }) {
    const update = (index: number, value: number | null) => {
      const next = [...(componentProps.modelValue ?? [componentProps.min ?? 0, componentProps.max ?? 127])] as [number, number];
      next[index] = value ?? next[index];
      emit('update:modelValue', next.sort((a, b) => a - b));
    };
    return () => h(NFormItem, { label: componentProps.label }, {
      default: () => h('div', { class: 'range-dual' }, [
        h(NInputNumber, { value: componentProps.modelValue?.[0], min: componentProps.min, max: componentProps.max, 'onUpdate:value': (value) => update(0, value) }),
        h(NInputNumber, { value: componentProps.modelValue?.[1], min: componentProps.min, max: componentProps.max, 'onUpdate:value': (value) => update(1, value) }),
      ]),
    });
  },
});
</script>

<style>
.dual, .range-dual {
  display: grid;
  align-items: center;
  grid-template-columns: minmax(0, 1fr) 120px;
  gap: 12px;
  width: 100%;
}

.range-dual {
  grid-template-columns: 1fr 1fr;
}
</style>

<style scoped>
.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 12px;
}

h4 {
  margin: 8px 0 12px;
}
</style>
