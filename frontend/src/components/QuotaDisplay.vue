<template>
  <div v-if="total != null && used != null">
    <el-progress
      :percentage="percentage"
      :color="progressColor"
      :stroke-width="14"
      :format="() => `${used} / ${total}`"
      style="min-width: 120px;"
    />
  </div>
  <span v-else style="color: #c0c4cc; font-size: 12px;">--</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: Number, default: null },
  used: { type: Number, default: null },
})

const percentage = computed(() => {
  if (!props.total || props.total === 0) return 0
  return Math.min(100, Math.round((props.used / props.total) * 100))
})

const progressColor = computed(() => {
  if (percentage.value > 90) return '#F56C6C'
  if (percentage.value > 70) return '#E6A23C'
  return '#67C23A'
})
</script>
