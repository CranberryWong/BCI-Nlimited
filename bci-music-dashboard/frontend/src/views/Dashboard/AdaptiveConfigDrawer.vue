<template>
  <n-drawer :show="show" :width="1100" style="max-width: 100vw" @update:show="$emit('update:show', $event)">
    <n-drawer-content title="Adaptive Performance Config · 演出配置" closable>
      <n-alert :type="adaptive.status?.config_locked ? 'warning' : 'info'" :title="adaptive.status?.config_locked ? '演出进行中 · 配置已锁定' : '配置将在下次演出生效'">
        {{ adaptive.status?.config_locked ? '请先停止当前演出，再保存或重置配置。' : '这里显示后端当前配置；保存当前页后，新的设置会在下一次演出启动时载入。' }}悬停或聚焦每项名称旁的 ⓘ 查看说明。
      </n-alert>
      <n-tabs v-model:value="active" type="line" style="margin-top: 20px">
        <n-tab-pane v-for="tab in tabs" :key="tab.id" :name="tab.id" :tab="tab.label">
          <div class="module-heading"><div><h2>{{ tab.label }}</h2><p>{{ tab.description }}</p></div><n-tag :bordered="false">{{ tab.id }} · 演出配置</n-tag></div>
          <ConfigNode :value="drafts[tab.id]" :path="tab.id" root @update:value="changed(tab.id, $event)" />
        </n-tab-pane>
      </n-tabs>
      <template #footer>
        <n-space justify="space-between" align="center">
          <span class="draft-status">{{ status }}</span>
          <n-space><n-popconfirm positive-text="确认恢复" negative-text="取消" @positive-click="reset"><template #trigger><n-button :disabled="adaptive.status?.config_locked">恢复当前页</n-button></template>放弃当前页尚未保存的修改，并恢复服务器中已保存的配置？</n-popconfirm><n-button type="primary" :disabled="adaptive.status?.config_locked" :loading="saving" @click="save">保存当前页</n-button></n-space>
        </n-space>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
<script setup lang="ts">
import { provide, ref, watch } from 'vue';
import { NAlert, NButton, NDrawer, NDrawerContent, NPopconfirm, NSpace, NTabPane, NTabs, NTag, useMessage } from 'naive-ui';
import { useAdaptiveStore } from '../../stores/adaptive';
import ConfigNode from './config/ConfigNode.vue';
import { defaults, tabs } from './config/catalog';
const props = defineProps<{ show: boolean }>();
defineEmits<{ 'update:show': [value: boolean] }>();
const adaptive = useAdaptiveStore();
const active = ref('inputs');
const drafts = ref<Record<string, any>>(structuredClone(defaults));
provide('configDrafts', drafts);
const status = ref('正在读取演出配置…');
const saving = ref(false);
const message = useMessage();
watch(() => props.show, async (show) => {
  if (!show) return;
  try {
    await adaptive.loadConfig();
    drafts.value = structuredClone(adaptive.modules);
    status.value = adaptive.status?.config_locked ? '演出进行中 · 配置只读' : '已载入当前演出配置';
  } catch { status.value = '读取配置失败'; message.error('无法读取演出配置'); }
}, { immediate: true });
function changed(id: string, value: any) { drafts.value[id] = value; status.value = '当前页有未保存修改'; }
async function reset() {
  try {
    await adaptive.resetModule(active.value);
    drafts.value[active.value] = structuredClone(adaptive.modules[active.value]);
    status.value = '当前页已恢复服务器中保存的配置';
    message.success('已恢复当前页');
  } catch (error) { message.error(error instanceof Error ? error.message : '重置失败'); }
}
async function save() {
  saving.value = true;
  try {
    await adaptive.saveModule(active.value, drafts.value[active.value]);
    drafts.value[active.value] = structuredClone(adaptive.modules[active.value]);
    status.value = '已保存 ' + new Date().toLocaleTimeString() + ' · 下次演出生效';
    message.success('当前页配置已保存');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '保存失败');
  } finally {
    saving.value = false;
  }
}
</script>
<style scoped>
.module-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; margin:12px 0 24px; }
h2 { font-size:22px; margin:0 0 8px; } p,.draft-status { color:#8d98ab; font-size:13px; } p { margin:0; }
</style>
