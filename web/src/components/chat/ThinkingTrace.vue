<script setup lang="ts">
import { ArrowDown, CircleCheck, CircleClose, Loading } from '@element-plus/icons-vue'
import { computed, ref, watch } from 'vue'

import type { ExecutionInfo, ExecutionTraceItem } from '@/types/chat'

const props = withDefaults(defineProps<{
  execution: ExecutionInfo
  active?: boolean
  defaultOpen?: boolean
}>(), {
  active: false,
  defaultOpen: false,
})

const open = ref(props.defaultOpen || props.active)
const latest = computed(() => (
  [...props.execution.trace].reverse().find((item) => item.status === 'running')
  ?? props.execution.trace.at(-1)
))
const summary = computed(() => {
  if (props.active && latest.value) return latest.value.label
  const completed = props.execution.trace.filter((item) => item.status === 'succeeded').length
  return completed ? `已完成 ${completed} 个执行步骤` : '执行过程'
})
const displayItems = computed(() => {
  let previousGroupId: string | undefined
  return props.execution.trace.map((item) => {
    const showGroupLabel = Boolean(item.groupId && item.groupId !== previousGroupId)
    previousGroupId = item.groupId
    return { ...item, showGroupLabel }
  })
})

watch(
  () => props.active,
  (active, wasActive) => {
    if (active) open.value = true
    else if (wasActive) open.value = false
  },
)

watch(
  () => props.execution.runId,
  () => { open.value = props.defaultOpen || props.active },
)

function formatDuration(durationMs?: number): string {
  if (durationMs === undefined) return ''
  return durationMs < 1_000 ? `${durationMs} ms` : `${(durationMs / 1_000).toFixed(1)} s`
}

function traceTypeLabel(type: ExecutionTraceItem['type']): string {
  const labels: Record<ExecutionTraceItem['type'], string> = {
    route: '路由',
    node: '节点',
    tool: '工具',
    retrieval: '检索',
    rewrite: '改写',
    plan: '计划',
    evaluation: '评估',
  }
  return labels[type]
}
</script>

<template>
  <section class="thinking-trace" :class="{ 'is-active': active }">
    <button
      type="button"
      class="thinking-trace-header"
      :aria-expanded="open"
      @click="open = !open"
    >
      <span class="thinking-trace-summary">
        <el-icon v-if="active" class="is-loading"><Loading /></el-icon>
        <el-icon v-else><CircleCheck /></el-icon>
        <span>{{ summary }}</span>
      </span>
      <el-icon class="thinking-trace-toggle" :class="{ 'is-open': open }"><ArrowDown /></el-icon>
    </button>

    <div v-show="open" class="thinking-trace-list">
      <template v-for="item in displayItems" :key="item.id">
        <p v-if="item.showGroupLabel" class="thinking-trace-group">{{ item.groupLabel }}</p>
        <div class="thinking-trace-item" :class="`is-${item.status}`">
          <el-icon v-if="item.status === 'running'" class="is-loading"><Loading /></el-icon>
          <el-icon v-else-if="item.status === 'failed'"><CircleClose /></el-icon>
          <el-icon v-else><CircleCheck /></el-icon>
          <div class="thinking-trace-content">
            <div class="thinking-trace-label">
              <span>{{ item.label }}</span>
              <small>{{ traceTypeLabel(item.type) }}</small>
              <time v-if="item.durationMs !== undefined">{{ formatDuration(item.durationMs) }}</time>
            </div>
            <p v-if="item.detail">{{ item.detail }}</p>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
