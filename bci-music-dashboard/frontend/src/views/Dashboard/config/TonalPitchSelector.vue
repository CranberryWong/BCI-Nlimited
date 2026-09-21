<template>
  <div class="pitch-selector">
    <div class="selector-toolbar">
      <span>已选 {{ modelValue.length }} / 12 个音级</span>
      <n-space size="small">
        <n-button size="tiny" @click="restore">恢复标准定义</n-button>
        <n-button size="tiny" @click="selectAll">全选十二音</n-button>
      </n-space>
    </div>
    <div class="pitch-grid">
      <button
        v-for="option in options"
        :key="option.value"
        type="button"
        :class="['pitch-button', { selected: modelValue.includes(option.value) }]"
        :aria-pressed="modelValue.includes(option.value)"
        :aria-label="`${modelValue.includes(option.value) ? '移除' : '选择'} ${option.label}`"
        :disabled="cannotRemove(option.value)"
        :title="option.value === 0 ? '主音是音阶基础，不能移除' : cannotRemove(option.value) ? '音阶至少保留三个音级' : ''"
        @click="toggle(option.value)"
      >
        <strong>{{ option.label }}</strong>
        <small>{{ option.caption }}</small>
      </button>
    </div>
    <p class="legend">数字表示相对主音的半音距离。高亮为当前音阶包含的音，未高亮仍可选择；主音固定保留，音阶至少包含三个音级。</p>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue';
import { NButton, NSpace } from 'naive-ui';
const props = defineProps<{ modelValue: number[]; scaleName: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: number[]] }>();
const degrees = ['主音','♭2','2','♭3','3','4','♯4 / ♭5','5','♭6','6','♭7','7'];
const presets: Record<string, number[]> = {
  gong:[0,2,4,7,9], shang:[0,2,5,7,10], jue:[0,3,5,8,10], zhi:[0,2,5,7,9],
  yu:[0,3,5,7,10], major:[0,2,4,5,7,9,11], minor:[0,2,3,5,7,8,10],
};
const options = computed(() => degrees.map((label, value) => ({ value, label, caption: `${value} 半音` })));
function ordered(values: number[]) {
  const order = options.value.map(option => option.value);
  return [...new Set(values)].sort((a, b) => order.indexOf(a) - order.indexOf(b));
}
function toggle(value: number) {
  if (cannotRemove(value)) return;
  emit('update:modelValue', props.modelValue.includes(value) ? props.modelValue.filter(item => item !== value) : ordered([...props.modelValue, value]));
}
function cannotRemove(value: number) { return props.modelValue.includes(value) && (value === 0 || props.modelValue.length <= 3); }
function restore() { emit('update:modelValue', [...(presets[props.scaleName] ?? [0,4,7])]); }
function selectAll() { emit('update:modelValue', options.value.map(option => option.value)); }
</script>
<style scoped>
.pitch-selector { width:100%; }
.selector-toolbar { display:flex; justify-content:space-between; align-items:center; gap:12px; color:#8290a2; font-size:12px; margin-bottom:12px; }
.pitch-grid { display:grid; grid-template-columns:repeat(6,minmax(84px,1fr)); gap:8px; }
.pitch-button { appearance:none; border:1px solid #8593a342; border-radius:8px; background:transparent; color:inherit; min-height:58px; padding:8px 6px; cursor:pointer; transition:.15s ease; }
.pitch-button:hover { border-color:#63e2b7; background:#63e2b70c; }
.pitch-button:disabled { cursor:not-allowed; opacity:.72; }
.pitch-button.selected { border-color:#36ad6a; background:#36ad6a1c; box-shadow:inset 0 0 0 1px #36ad6a55; }
.pitch-button strong,.pitch-button small { display:block; } .pitch-button strong { font-size:14px; } .pitch-button small { color:#8795a8; margin-top:4px; font-size:10px; }
.legend { color:#8795a8; font-size:11px; line-height:1.5; margin:10px 0 0; }
@media(max-width:700px) { .pitch-grid { grid-template-columns:repeat(3,minmax(74px,1fr)); } .selector-toolbar { align-items:flex-start; flex-direction:column; } }
</style>
