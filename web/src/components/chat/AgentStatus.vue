<script setup lang="ts">
import { Loading } from '@element-plus/icons-vue'

import type { ExecutionInfo } from '@/types/chat'

defineProps<{
  status: string | null
  execution: ExecutionInfo | null
}>()
</script>

<template>
  <div v-if="status" class="agent-status">
    <el-icon class="is-loading"><Loading /></el-icon>
    <span>{{ status }}</span>
    <span v-if="execution?.route" class="route-badge">
      {{ execution.route === 'general_chat' ? 'General' : execution.route === 'react' ? 'ReAct' : 'Plan-Execute' }}
    </span>
  </div>
</template>
