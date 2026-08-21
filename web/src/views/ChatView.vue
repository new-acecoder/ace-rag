<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

import AgentStatus from '@/components/chat/AgentStatus.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ConversationList from '@/components/chat/ConversationList.vue'
import ExecutionDrawer from '@/components/chat/ExecutionDrawer.vue'
import MessageList from '@/components/chat/MessageList.vue'
import SourceDrawer from '@/components/chat/SourceDrawer.vue'
import { useConversationStore } from '@/stores/conversation'
import type { ChatMessage, ExecutionInfo, Source } from '@/types/chat'

const conversation = useConversationStore()
const selectedSource = ref<Source | null>(null)
const sourceDrawerOpen = ref(false)
const executionDrawerOpen = ref(false)
const selectedExecution = ref<ExecutionInfo | null>(null)

onMounted(() => void conversation.initialize())
onUnmounted(() => void conversation.stopChat())

function openSource(source: Source): void {
  selectedSource.value = source
  sourceDrawerOpen.value = true
}

function openExecution(message: ChatMessage): void {
  selectedExecution.value = message.execution ?? null
  executionDrawerOpen.value = true
}
</script>

<template>
  <section class="chat-view">
    <ConversationList
      :conversations="conversation.conversations"
      :current-conversation-id="conversation.currentConversationId"
      @create="conversation.createConversation"
      @select="conversation.selectConversation"
    />
    <main class="chat-main">
      <header class="chat-titlebar">
        <div>
          <p class="eyebrow">智能问答</p>
          <h1>向知识库提问</h1>
        </div>
        <el-button text :loading="conversation.loadingHistory" @click="conversation.refreshConversation()">
          刷新状态
        </el-button>
      </header>
      <AgentStatus :status="conversation.currentStatus" :execution="conversation.execution" />
      <p v-if="conversation.error" class="chat-error">{{ conversation.error }}</p>
      <MessageList
        :messages="conversation.messages"
        @source="openSource"
        @execution="openExecution"
        @resume="conversation.resumeTurn"
      />
      <ChatInput
        :disabled="!conversation.canSend"
        :streaming="conversation.streaming"
        :thinking-enabled="conversation.thinkingEnabled"
        @submit="conversation.sendMessage"
        @stop="conversation.stopChat"
        @update:thinking-enabled="conversation.setThinkingEnabled"
      />
    </main>
    <SourceDrawer v-model:open="sourceDrawerOpen" :source="selectedSource" />
    <ExecutionDrawer v-model:open="executionDrawerOpen" :execution="selectedExecution" />
  </section>
</template>
