<script setup lang="ts">
import { ChatDotRound, Plus } from '@element-plus/icons-vue'

import type { Conversation } from '@/types/chat'

defineProps<{
  conversations: Conversation[]
  currentConversationId: string | null
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  create: []
}>()
</script>

<template>
  <aside class="conversation-sidebar" aria-label="历史会话">
    <el-button class="new-conversation" type="primary" :icon="Plus" @click="emit('create')">
      新建对话
    </el-button>
    <p class="conversation-label">历史会话</p>
    <div class="conversation-list">
      <button
        v-for="conversation in conversations"
        :key="conversation.conversationId"
        class="conversation-item"
        :class="{ 'is-active': conversation.conversationId === currentConversationId }"
        type="button"
        @click="emit('select', conversation.conversationId)"
      >
        <el-icon><ChatDotRound /></el-icon>
        <span>{{ conversation.title }}</span>
      </button>
    </div>
  </aside>
</template>
