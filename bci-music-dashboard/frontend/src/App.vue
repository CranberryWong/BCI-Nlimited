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
    primaryColor: '#000000',
    primaryColorHover: '#000000',
    primaryColorPressed: '#000000',
    primaryColorSuppl: '#000000',
    successColor: '#000000',
    successColorHover: '#000000',
    warningColor: '#000000',
    borderRadius: '0px',
  },
};
</script>
