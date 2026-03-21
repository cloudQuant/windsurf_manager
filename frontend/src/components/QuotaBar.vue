<template>
  <div style="min-width: 100px;">
    <el-progress
      :percentage="pct"
      :color="progressColor"
      :stroke-width="14"
      :format="() => pct.toFixed(1) + '%'"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  pct: { type: Number, required: true },
  label: { type: String, default: '' },
})

const progressColor = computed(() => {
  if (props.pct <= 10) return '#F56C6C'
  if (props.pct <= 30) return '#E6A23C'
  return '#67C23A'
})
</script>
