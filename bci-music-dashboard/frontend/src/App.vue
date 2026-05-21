<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <Dashboard />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { NConfigProvider, NMessageProvider, type GlobalThemeOverrides } from 'naive-ui';
import Dashboard from './views/Dashboard/index.vue';

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#1769aa',
    primaryColorHover: '#2780c2',
    successColor: '#2d8a5b',
    warningColor: '#bf6a00',
    borderRadius: '6px',
  },
};
</script>
