<template>
  <n-drawer :show="show" :width="760" @update:show="$emit('update:show', $event)">
    <n-drawer-content title="Adaptive Performance Config" closable>
      <n-alert v-if="locked" type="warning" title="演出中配置已锁定">停止演出后才能保存修改。</n-alert>
      <n-tabs v-model:value="active" type="line" animated>
        <n-tab-pane v-for="(_, name) in modules" :key="name" :name="name" :tab="name">
          <n-input v-model:value="drafts[name]" type="textarea" :autosize="{ minRows: 22, maxRows: 32 }" :disabled="locked" />
        </n-tab-pane>
      </n-tabs>
      <template #footer>
        <n-space justify="end">
          <n-button @click="reload">恢复当前值</n-button>
          <n-button type="primary" :disabled="locked || !active" @click="save">保存 {{ active }}</n-button>
        </n-space>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue';
import { NAlert, NButton, NDrawer, NDrawerContent, NInput, NSpace, NTabPane, NTabs, useMessage } from 'naive-ui';

const props = defineProps<{ show: boolean; locked: boolean; modules: Record<string, Record<string, unknown>> }>();
const emit = defineEmits<{ 'update:show': [value: boolean]; save: [module: string, config: Record<string, unknown>] }>();
const message = useMessage();
const active = ref('inputs');
const drafts = reactive<Record<string, string>>({});
function reload() {
  for (const [name, config] of Object.entries(props.modules)) drafts[name] = JSON.stringify(config, null, 2);
  if (!props.modules[active.value]) active.value = Object.keys(props.modules)[0] || '';
}
function save() {
  try {
    emit('save', active.value, JSON.parse(drafts[active.value]));
  } catch (error) {
    message.error(error instanceof Error ? error.message : 'JSON 格式无效');
  }
}
watch(() => props.modules, reload, { deep: true });
watch(() => props.show, (shown) => { if (shown) reload(); });
onMounted(reload);
</script>
