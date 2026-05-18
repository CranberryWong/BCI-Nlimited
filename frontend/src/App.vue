<template>
  <div class="shell">
    <aside class="sidebar">
      <button class="menu" aria-label="Menu">☰</button>
      <input class="search" value="Find a setting" readonly />
      <nav>
        <button :class="{ active: activeTab === 'general' }" @click="activeTab = 'general'">General</button>
        <button :class="{ active: activeTab === 'audio' }" @click="activeTab = 'audio'">Audio / MIDI</button>
        <button :class="{ active: activeTab === 'test' }" @click="activeTab = 'test'">Test Stream</button>
      </nav>
    </aside>

    <main class="content">
      <header class="page-header">
        <div class="status-dot" :class="{ on: state.running }"></div>
        <div>
          <h1>{{ pageTitle }}</h1>
          <p>{{ statusText }}</p>
        </div>
      </header>

      <section v-if="activeTab === 'general'" class="panel">
        <h2>Networking</h2>
        <div class="grid">
          <label>Root Folder <input v-model="draft.xdf_root_dir" /></label>
          <label>Session Keyword <input v-model="draft.session_keyword" /></label>
          <label>Model Path <input v-model="draft.model_path" /></label>
          <label>Server Mode <input :value="state.mode" readonly /></label>
        </div>
        <div class="actions">
          <button class="primary" @click="start('xdf')">Start XDF</button>
          <button @click="stop">Shut down</button>
          <button @click="saveConfig">Save Config</button>
        </div>
        <TelemetryCard :latest="latest" />
      </section>

      <section v-if="activeTab === 'audio'" class="panel">
        <h2>Audio / MIDI</h2>
        <div class="grid">
          <label>OSC IP <input v-model="draft.osc_target_ip" /></label>
          <label>OSC Port <input v-model.number="draft.osc_target_port" type="number" /></label>
          <label>OSC Address <input v-model="draft.osc_address" /></label>
          <label class="toggle"><input v-model="draft.midi_enabled" type="checkbox" /> Enable MIDI</label>
          <label>MIDI Port
            <select v-model="draft.midi_port_name">
              <option value="">Auto select</option>
              <option v-for="port in midiPorts" :key="port" :value="port">{{ port }}</option>
            </select>
          </label>
          <label>Valence CC <input v-model.number="draft.valence_cc" type="number" min="0" max="127" /></label>
          <label>Arousal CC <input v-model.number="draft.arousal_cc" type="number" min="0" max="127" /></label>
          <label>Confidence CC <input v-model.number="draft.confidence_cc" type="number" min="0" max="127" /></label>
        </div>
        <div class="actions">
          <button class="primary" @click="saveConfig">Apply</button>
        </div>
        <div class="status-grid">
          <span>OSC {{ state.osc_ready ? 'Ready' : (state.osc_error || 'Unavailable') }}</span>
          <span>MIDI {{ state.midi_ready ? 'Ready' : (state.midi_error || 'Unavailable') }}</span>
        </div>
        <TelemetryCard :latest="latest" />
      </section>

      <section v-if="activeTab === 'test'" class="panel">
        <h2>Test Stream</h2>
        <div class="actions">
          <button class="primary" @click="start('test')">Start Test Stream</button>
          <button @click="stopTest">Stop Test Stream</button>
        </div>
        <TelemetryCard :latest="latest" />
        <p class="path">Validation target: {{ draft.osc_target_ip }}:{{ draft.osc_target_port }} {{ draft.osc_address }}</p>
      </section>

      <footer>{{ state.last_log || state.last_error || 'Ready' }}</footer>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import TelemetryCard from './TelemetryCard.vue'

const activeTab = ref('general')
const state = reactive({ latest: {}, running: false, mode: 'idle' })
const latest = computed(() => state.latest || {})
const draft = reactive({})
const midiPorts = ref([])

const pageTitle = computed(() => activeTab.value === 'audio' ? 'Audio' : activeTab.value === 'test' ? 'Test Stream' : 'General')
const statusText = computed(() => state.running ? 'Successful' : 'Stopped')

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!response.ok) throw new Error(await response.text())
  return response.json()
}

function assignConfig(config) {
  Object.keys(draft).forEach((key) => delete draft[key])
  Object.assign(draft, config)
}

async function refresh(includeConfig = false) {
  const payload = await api('/api/status')
  Object.assign(state, payload.state)
  if (includeConfig) assignConfig(payload.config)
  midiPorts.value = payload.midi_ports || []
}

async function saveConfig() {
  const config = await api('/api/config', {
    method: 'PUT',
    body: JSON.stringify(draft)
  })
  assignConfig(config)
  await refresh(false)
}

async function start(mode) {
  await saveConfig()
  const next = await api('/api/start', {
    method: 'POST',
    body: JSON.stringify({ mode })
  })
  Object.assign(state, next)
}

async function stop() {
  const next = await api('/api/stop', { method: 'POST' })
  Object.assign(state, next)
}

async function stopTest() {
  const next = await api('/api/test-stream/stop', { method: 'POST' })
  Object.assign(state, next)
}

onMounted(async () => {
  await refresh(true)
  setInterval(() => refresh(false), 1000)
})
</script>
