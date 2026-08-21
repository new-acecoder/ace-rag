<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import AssistantMessage from './AssistantMessage.vue'
import type { ChatMessage, Source } from '@/types/chat'

const props = defineProps<{ messages: ChatMessage[] }>()
const emit = defineEmits<{
  source: [source: Source]
  execution: [message: ChatMessage]
  resume: [turnId: string]
}>()

const scrollPanel = ref<HTMLElement | null>(null)

watch(
  () => props.messages
    .map((message) => `${message.id}:${message.content.length}:${message.status}:${message.execution?.lastSeq ?? 0}`)
    .join('|'),
  async () => {
    await nextTick()
    if (scrollPanel.value) scrollPanel.value.scrollTop = scrollPanel.value.scrollHeight
  },
)
</script>

<template>
  <div ref="scrollPanel" class="message-list" aria-live="polite">
    <template v-if="messages.length">
      <template v-for="message in messages" :key="message.id">
        <article v-if="message.role === 'user'" class="message message-user">
          <div class="message-body">{{ message.content }}</div>
        </article>
        <AssistantMessage
          v-else
          :message="message"
          @source="emit('source', $event)"
          @execution="emit('execution', $event)"
          @resume="emit('resume', $event)"
        />
      </template>
    </template>
    <div v-else class="chat-empty">
      <span class="empty-mark">A</span>
      <p class="eyebrow">ACE RAG</p>
      <h1>企业智能知识助手</h1>
      <p>你可以询问知识库中的制度、流程和业务资料。</p>
    </div>
  </div>
</template>
