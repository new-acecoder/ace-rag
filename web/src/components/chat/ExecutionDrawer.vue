<script setup lang="ts">
import type { ExecutionInfo } from '@/types/chat'
import ThinkingTrace from './ThinkingTrace.vue'

defineProps<{
  open: boolean
  execution: ExecutionInfo | null
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <el-drawer :model-value="open" title="执行过程" size="420px" @update:model-value="emit('update:open', $event)">
    <template v-if="execution">
      <p class="execution-route">
        {{ execution.route === 'plan_execute' ? 'Plan-Execute-Replan' : execution.route === 'react' ? 'ReAct' : 'General Chat' }}
        <span v-if="execution.routeReason">· {{ execution.routeReason }}</span>
      </p>
      <section v-if="execution.plan?.length" class="execution-section">
        <h3>任务计划</h3>
        <ol class="plan-list">
          <li v-for="step in execution.plan" :key="step.stepId" :class="`is-${step.status}`">
            <span>{{ step.goal }}</span>
            <small>{{ step.status === 'not_run' ? '未继续' : step.status }}</small>
          </li>
        </ol>
      </section>
      <section class="execution-section">
        <h3>完整时间线</h3>
        <ThinkingTrace
          v-if="execution.trace.length"
          :key="execution.runId"
          :execution="execution"
          default-open
        />
        <p v-else class="execution-empty">本次执行没有可展示的实时轨迹。</p>
      </section>
    </template>
  </el-drawer>
</template>
