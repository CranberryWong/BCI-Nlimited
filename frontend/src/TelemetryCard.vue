<template>
  <div class="telemetry">
    <div>
      <span>Valence</span>
      <strong>{{ latest.valence ?? 5 }}</strong>
    </div>
    <div>
      <span>Arousal</span>
      <strong>{{ latest.arousal ?? 5 }}</strong>
    </div>
    <div>
      <span>Prob0</span>
      <strong>{{ format(latest.prob0) }}</strong>
    </div>
    <div>
      <span>Prob1</span>
      <strong>{{ format(latest.prob1) }}</strong>
    </div>
    <div>
      <span>Source</span>
      <strong>{{ latest.source || 'idle' }}</strong>
    </div>
  </div>
</template>

<script setup>
defineProps({
  latest: {
    type: Object,
    default: () => ({})
  }
})

function format(value) {
  return value === null || value === undefined ? '-' : Number(value).toFixed(2)
}
</script>

