<template>
  <n-drawer :show="show" width="760" @update:show="$emit('update:show', $event)">
    <n-drawer-content title="Music Config" closable>
      <template v-if="draft">
        <n-tabs type="line">
          <n-tab-pane name="global" tab="Global Music Settings">
            <div class="settings-grid">
              <template v-for="field in globalFields" :key="field">
                <n-form-item :label="fieldLabel[field]">
                  <template v-if="optionsFor(field).length">
                    <n-select v-model:value="draft.global[field]" :options="optionsFor(field)" />
                  </template>
                  <template v-else>
                    <div class="dual">
                      <n-slider v-model:value="numericGlobal[field]" :min="bounds(field).min" :max="bounds(field).max" :step="field === 'bpm' ? 1 : 0.01" @update:value="draft.global[field] = $event" />
                      <n-input-number v-model:value="numericGlobal[field]" :min="bounds(field).min" :max="bounds(field).max" :step="field === 'bpm' ? 1 : 0.01" @update:value="draft.global[field] = $event ?? bounds(field).min" />
                    </div>
                  </template>
                </n-form-item>
              </template>
            </div>
          </n-tab-pane>
          <n-tab-pane name="profiles" tab="Emotion Profiles">
            <n-collapse>
              <n-collapse-item v-for="(profile, label) in draft.emotion_profiles" :key="label" :title="String(label)">
                <div class="settings-grid">
                  <n-form-item label="中文标签"><n-input v-model:value="profile.label_zh" /></n-form-item>
                  <n-form-item label="Scale"><n-input v-model:value="profile.scale" /></n-form-item>
                  <n-form-item label="Chord Quality"><n-input v-model:value="profile.chord_quality" /></n-form-item>
                  <range-input v-for="field in rangeFields" :key="field" :label="field" :model-value="rangeValue(profile, field)" @update:model-value="profile[field] = $event" />
                  <profile-scalar label="Brightness" v-model="profile.brightness" />
                  <profile-scalar label="Tension" v-model="profile.tension" />
                </div>
              </n-collapse-item>
            </n-collapse>
          </n-tab-pane>
          <n-tab-pane name="yaml" tab="YAML / Preset">
            <div class="toolbar-gap">
              <n-input v-model:value="presetName" placeholder="Preset name" />
              <n-button @click="savePreset">Save Preset</n-button>
              <n-button @click="exportYaml">Export YAML</n-button>
              <n-upload :show-file-list="false" accept=".yaml,.yml,.json" :custom-request="importConfig">
                <n-button>Import</n-button>
              </n-upload>
            </div>
            <div class="preset-section">
              <div class="preset-heading">
                <strong>Presets</strong>
                <span>{{ selectedPreset ? 'Current preset selected' : 'No preset selected' }}</span>
              </div>
              <n-radio-group
                :value="selectedPreset"
                class="preset-list"
                @update:value="loadPreset"
              >
                <label
                  v-for="preset in presets"
                  :key="preset.id"
                  class="preset-row"
                  :class="{ active: preset.id === selectedPreset }"
                >
                  <n-radio :value="preset.id" />
                  <span class="preset-name">{{ preset.name }}</span>
                  <n-tag v-if="preset.builtin" size="small" :bordered="false">Built-in</n-tag>
                  <n-tag v-else size="small" type="success" :bordered="false">Custom</n-tag>
                  <span v-if="preset.id === selectedPreset" class="current-label">Current</span>
                </label>
              </n-radio-group>
            </div>
          </n-tab-pane>
        </n-tabs>
      </template>
      <template #footer>
        <div class="toolbar-gap">
          <n-button @click="$emit('reset')">Reset</n-button>
          <n-button type="primary" @click="draft && $emit('apply', draft)">Apply</n-button>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { NButton, NCollapse, NCollapseItem, NDrawer, NDrawerContent, NFormItem, NInput, NInputNumber, NRadio, NRadioGroup, NSelect, NSlider, NTabPane, NTag, NTabs, NUpload, type UploadCustomRequestOptions } from 'naive-ui';
import { defineComponent, h, onMounted, reactive, ref, watch } from 'vue';
import { api, downloadConfig } from '../../api/client';
import type { EmotionProfile, MusicConfig } from '../../types';

const props = defineProps<{ show: boolean; config: MusicConfig | null }>();
const emit = defineEmits(['update:show', 'apply', 'reset', 'loaded']);
const draft = ref<MusicConfig | null>(null);
const presetName = ref('');
const selectedPreset = ref<string | null>(null);
const presets = ref<{ id: string; name: string; builtin: boolean; active: boolean }[]>([]);
const numericGlobal = reactive<Record<string, number>>({});
watch(() => props.config, (config) => {
  draft.value = config ? JSON.parse(JSON.stringify(config)) : null;
  if (config) Object.entries(config.global).forEach(([key, value]) => {
    if (typeof value === 'number') numericGlobal[key] = value;
  });
}, { immediate: true });

const globalFields = ['bpm', 'root_note', 'scale', 'quantization', 'swing', 'humanize', 'master_velocity', 'master_density', 'output_mode'];
const fieldLabel: Record<string, string> = {
  bpm: 'BPM', root_note: 'Root Note', scale: 'Scale', quantization: 'Quantization', swing: 'Swing',
  humanize: 'Humanize', master_velocity: 'Master Velocity', master_density: 'Master Density', output_mode: 'Output Mode',
};
const rangeFields = ['bpm_range', 'pitch_range', 'velocity_range', 'density_range', 'delay_ms_range'];
function rangeValue(profile: EmotionProfile, field: string) {
  return profile[field] as number[];
}
function defaultSchema(field: string) {
  return ((props.config?.default_schema?.global as Record<string, Record<string, unknown>> | undefined)?.[field]) ?? {};
}
function optionsFor(field: string) {
  return ((defaultSchema(field).options as string[] | undefined) ?? []).map((value) => ({ label: value, value }));
}
function bounds(field: string) {
  const item = defaultSchema(field);
  return { min: Number(item.min ?? 0), max: Number(item.max ?? (field === 'bpm' ? 220 : 1)) };
}
async function loadPresets() {
  presets.value = (await api.get('/presets')).data;
  selectedPreset.value = presets.value.find((preset) => preset.active)?.id ?? null;
}
async function savePreset() {
  const saved = (await api.post('/presets', { name: presetName.value || 'Dashboard Preset' })).data;
  await loadPresets();
  selectedPreset.value = saved.id;
  presetName.value = '';
}
async function loadPreset(id: string) {
  const config = (await api.post(`/presets/${id}/load`)).data;
  selectedPreset.value = id;
  presets.value = presets.value.map((preset) => ({ ...preset, active: preset.id === id }));
  emit('loaded', config);
}
async function importConfig(options: UploadCustomRequestOptions) {
  const form = new FormData();
  form.append('file', options.file.file as File);
  emit('loaded', (await api.post('/music/config/import', form)).data);
  options.onFinish();
}
function exportYaml() {
  downloadConfig();
}
onMounted(loadPresets);

const RangeInput = defineComponent({
  props: { modelValue: Array<number>, label: String },
  emits: ['update:modelValue'],
  setup(componentProps, { emit: localEmit }) {
    return () => h(NFormItem, { label: componentProps.label }, {
      default: () => h('div', { class: 'range-dual' }, [0, 1].map((index) =>
        h(NInputNumber, {
          value: componentProps.modelValue?.[index],
          'onUpdate:value': (value: number | null) => {
            const next = [...(componentProps.modelValue ?? [0, 1])];
            next[index] = value ?? next[index];
            localEmit('update:modelValue', next);
          },
        }),
      )),
    });
  },
});
const ProfileScalar = defineComponent({
  props: { modelValue: Number, label: String },
  emits: ['update:modelValue'],
  setup(componentProps, { emit: localEmit }) {
    return () => h(NFormItem, { label: componentProps.label }, {
      default: () => h('div', { class: 'dual' }, [
        h(NSlider, { value: componentProps.modelValue, min: 0, max: 1, step: 0.01, 'onUpdate:value': (value) => localEmit('update:modelValue', value) }),
        h(NInputNumber, { value: componentProps.modelValue, min: 0, max: 1, step: 0.01, 'onUpdate:value': (value) => localEmit('update:modelValue', value ?? 0) }),
      ]),
    });
  },
});
</script>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.n-select {
  width: 100%;
}

.preset-section {
  margin-top: 22px;
}

.preset-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
}

.preset-heading span {
  color: #5f6872;
  font-size: 12px;
}

.preset-list {
  display: grid;
  border: 1px solid #d9dde3;
  border-radius: 0;
  overflow: hidden;
}

.preset-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 10px;
  min-height: 48px;
  padding: 8px 12px;
  background: #fff;
  cursor: pointer;
}

.preset-row + .preset-row {
  border-top: 1px solid #d9dde3;
}

.preset-row:hover,
.preset-row.active {
  background: #f3f5f7;
}

.preset-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.current-label {
  color: #111;
  font-size: 12px;
  font-weight: 600;
}
</style>
