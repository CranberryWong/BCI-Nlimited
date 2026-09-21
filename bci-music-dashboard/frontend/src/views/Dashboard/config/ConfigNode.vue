<template>
  <section :class="['config-node', { group: objectValue && !root, list: Array.isArray(value), root }]">
    <div v-if="!root" class="field-heading">
      <n-tooltip :show="helpOpen" :style="{ maxWidth: '360px' }">
        <template #trigger><span tabindex="0" class="field-label" @mouseenter="helpOpen = true" @mouseleave="helpOpen = false" @focus="helpOpen = true" @blur="helpOpen = false">{{ meta.label }} <span class="help-icon">ⓘ</span></span></template>
        {{ meta.help }}
      </n-tooltip>
      <span class="field-key">{{ path.split('.').at(-1) }}</span>
      <n-button v-if="/^form\.transitions\.[^.]+$/.test(path)" size="tiny" title="删除此起点的转场规则" @click="deleteTransition">删除规则</n-button>
    </div>
    <TonalPitchSelector v-if="/^tonal\.scales\.[^.]+$/.test(path)" :model-value="value" :scale-name="path.split('.').slice(-1)[0]" @update:model-value="$emit('update:value', $event)" />
    <n-collapse v-else-if="path === 'tonal.scales'" class="advanced-collapse">
      <n-collapse-item name="scale-definitions" title="展开并编辑音阶定义（高级）">
        <n-alert type="warning" :bordered="false">正常使用只需选择基础调式。修改定义会改变该调式允许的音，请在确认音阶结构时使用。</n-alert>
        <div class="children scale-children">
          <ConfigNode v-for="(item, key) in value" :key="key" :value="item" :path="`${path}.${key}`" @update:value="updateKey(String(key), $event)" />
        </div>
      </n-collapse-item>
    </n-collapse>
    <template v-else-if="objectValue">
      <div class="children">
        <ConfigNode v-for="(item, key) in value" :key="key" :value="item" :path="`${path}.${key}`" @update:value="updateKey(String(key), $event)" />
      </div>
      <div v-if="path === 'form.transitions'" class="add-key"><n-select v-model:value="newKey" :options="sectionOptions" placeholder="新转场起点（乐段标识）" aria-label="新转场起点" /><n-button :disabled="!newKey.trim() || newKey in value" @click="addKey">添加起点</n-button></div>
    </template>
    <template v-else-if="Array.isArray(value)">
      <p class="help-text">{{ meta.help }}</p>
      <div v-for="(item, index) in value" :key="index" class="list-row">
        <span class="ordinal">{{ index + 1 }}</span>
        <ConfigNode class="list-field" :value="item" :path="`${path}.${index}`" @update:value="updateIndex(index, $event)" />
        <div class="row-actions">
          <n-button size="tiny" :disabled="index === 0" :aria-label="`上移第 ${index+1} 项`" title="上移此项" @click="move(index, -1)">↑</n-button>
          <n-button size="tiny" :disabled="index === value.length-1" :aria-label="`下移第 ${index+1} 项`" title="下移此项" @click="move(index, 1)">↓</n-button>
          <n-button v-if="!range" size="tiny" :aria-label="`删除第 ${index+1} 项`" title="删除此项" @click="remove(index)">删除</n-button>
        </div>
      </div>
      <n-button v-if="!range" size="small" dashed @click="add">＋ 添加{{ path === 'form.sections' ? '乐段' : path === 'outputs.osc.targets' ? '目标' : '一项' }}</n-button>
    </template>
    <div v-else class="control">
      <n-switch v-if="typeof value === 'boolean'" :value="value" :aria-label="meta.label" @update:value="$emit('update:value', $event)"><template #checked>开启</template><template #unchecked>关闭</template></n-switch>
      <n-select v-else-if="options" :value="value" :options="options" :aria-label="meta.label" @update:value="$emit('update:value', $event)" />
      <n-input-number v-else-if="numeric" :value="value" v-bind="limits" :aria-label="meta.label" :placeholder="value === null ? '未设置' : ''" @update:value="setNumber" />
      <n-input v-else :value="value ?? ''" :type="path.endsWith('prompt_template') ? 'textarea' : 'text'" :autosize="{ minRows: 3 }" :placeholder="path.endsWith('output_device') ? '系统默认设备' : '请输入'" :aria-label="meta.label" @update:value="$emit('update:value', $event || (path.endsWith('output_device') ? null : ''))" />
      <small v-if="path.endsWith('frame_hz') || options?.length === 1">当前方案固定值</small>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, inject, ref, type Ref } from 'vue';
import { NAlert, NButton, NCollapse, NCollapseItem, NInput, NInputNumber, NSelect, NSwitch, NTooltip } from 'naive-ui';
import { bounds, choices, info, names } from './catalog';
import TonalPitchSelector from './TonalPitchSelector.vue';
const props = defineProps<{ value: any; path: string; root?: boolean }>();
const helpOpen = ref(false);
const drafts = inject<Ref<Record<string, any>>>('configDrafts');
const sectionOptions = computed(() => (drafts?.value.form.sections ?? []).map((section: any) => ({ value: section.id, label: `${section.id} · ${names[section.role] || section.role}` })));
const emit = defineEmits<{ 'update:value': [value: any] }>();
const newKey = ref('');
const meta = computed(() => info(props.path));
const objectValue = computed(() => props.value !== null && typeof props.value === 'object' && !Array.isArray(props.value));
const numeric = computed(() => typeof props.value === 'number' || /\.(latitude|longitude)$/.test(props.path));
const limits = computed(() => bounds(props.path));
const range = computed(() => /\.(melody_range|pitch_range)$/.test(props.path));
const options = computed(() => /^form\.transitions\.[^.]+\.\d+$/.test(props.path) ? sectionOptions.value : choices(props.path)?.map(value => ({ value, label: names[String(value)] ? `${names[String(value)]} · ${value}` : String(value) })));
function deleteTransition() { emit('update:value', undefined); }
function setNumber(value: number | null) { if (value !== null || /\.(latitude|longitude)$/.test(props.path)) emit('update:value', value); }
function updateKey(key: string, value: any) { const next = { ...props.value }; if (value === undefined) delete next[key]; else next[key] = value; emit('update:value', next); }
function updateIndex(index: number, value: any) { const list = [...props.value]; list[index] = value; emit('update:value', list); }
function remove(index: number) { emit('update:value', props.value.filter((_: any, i: number) => i !== index)); }
function move(index: number, direction: number) { const list = [...props.value]; [list[index], list[index+direction]] = [list[index+direction], list[index]]; emit('update:value', list); }
function addKey() { updateKey(newKey.value.trim(), []); newKey.value = ''; }
function add() {
  let item: any = choices(props.path)?.[0] ?? '';
  if (props.path.startsWith('form.transitions.')) item = sectionOptions.value[0]?.value ?? '';
  if (props.path === 'form.sections') item = { id: `section_${Date.now().toString(36)}`, role: 'identity' };
  else if (props.path === 'outputs.osc.targets') item = { id: `target_${Date.now().toString(36)}`, host: '127.0.0.1', port: 9000, enabled: true };
  else if (typeof props.value[0] === 'number' || /scales\.|strong_beat_degrees|anchors.beats/.test(props.path)) item = 0;
  emit('update:value', [...props.value, item]);
}
</script>
<style scoped>
.config-node { min-width:0; padding:12px 0; }
.group { border:1px solid #8593a32d; border-radius:12px; padding:18px; margin:10px 0; background:#8197b506; }
.children { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px 24px; }
.children > .group, .children > .list { grid-column:1 / -1; }
.field-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
.field-label { font-size:14px; font-weight:550; cursor:help; border-radius:4px; }
.field-label:focus { outline:2px solid #63e2b7; outline-offset:3px; }
.help-icon { color:#69bca5; font-weight:400; margin-left:4px; }
.field-key { font-size:10px; color:#8593a3; overflow-wrap:anywhere; }
.help-text { color:#8997a9; font-size:12px; margin:0 0 12px; line-height:1.6; }
.control { max-width:100%; } .control small { display:block; color:#8593a3; margin-top:6px; }
.control :deep(.n-input), .control :deep(.n-input-number) { width:100%; }
.list-row { display:flex; gap:10px; align-items:center; border-top:1px solid #8593a31c; padding:4px 0; }
.list-field { flex:1; } .ordinal { color:#6c9b91; font-size:12px; } .row-actions { display:flex; gap:4px; }
.add-key { display:flex; gap:8px; margin-top:12px; }
.advanced-collapse { border:1px solid #8593a32d; border-radius:10px; padding:0 14px; }
.scale-children { margin-top:12px; }
@media(max-width:700px) { .children { grid-template-columns:1fr; gap:8px; } .field-key { display:none; } .row-actions { flex-direction:column; } .group { padding:12px; } }
</style>
