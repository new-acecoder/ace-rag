<script setup lang="ts">
import MarkdownIt from 'markdown-it'
import { CopyDocument, Connection, Operation, View } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { ChatMessage, Source } from '@/types/chat'
import ThinkingTrace from './ThinkingTrace.vue'

const props = defineProps<{ message: ChatMessage }>()
const emit = defineEmits<{
  source: [source: Source]
  execution: [message: ChatMessage]
  resume: [turnId: string]
}>()

const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true })
const renderedContent = computed(() => markdown.render(props.message.content))

async function copyAnswer(): Promise<void> {
  await navigator.clipboard?.writeText(props.message.content)
}
</script>

<template>
  <article class="message message-assistant">
    <div class="message-avatar">A</div>
    <div class="assistant-content">
      <ThinkingTrace
        v-if="message.execution?.trace.length"
        :key="message.execution.runId"
        :execution="message.execution"
        :active="message.status === 'streaming' || message.status === 'stopping'"
      />
      <div v-if="message.status === 'streaming' && !message.content && !message.execution?.trace.length" class="answer-pending">
        <el-icon class="is-loading"><Connection /></el-icon>
        正在准备回答…
      </div>
      <div v-else-if="message.status === 'stopping'" class="answer-pending">
        <el-icon class="is-loading"><Connection /></el-icon>
        正在停止执行…
      </div>
      <div v-else-if="message.status === 'stopped'" class="answer-stopped">
        执行已停止，可以从最近的检查点继续。
        <el-button type="primary" text :icon="Operation" @click="emit('resume', message.turnId)">
          继续执行
        </el-button>
      </div>
      <div v-else-if="message.status === 'error' && !message.content" class="answer-error">
        本轮执行未完成，请刷新状态或在可恢复时继续执行。
      </div>
      <div v-if="message.content" class="markdown-answer" v-html="renderedContent" />

      <p v-if="message.answerStatus === 'best_effort'" class="best-effort-note">
        已达到执行上限，以下为基于当前证据的尽力回答。
      </p>

      <section v-if="message.sources?.length" class="source-list" aria-label="参考来源">
        <p>参考来源</p>
        <button
          v-for="source in message.sources"
          :key="source.chunkId"
          type="button"
          class="source-citation"
          @click="emit('source', source)"
        >
          [{{ source.citationIndex }}] {{ source.title }}
          <template v-if="source.pageNumber !== null"> · P{{ source.pageNumber }}</template>
        </button>
      </section>

      <div v-if="message.status === 'done' || message.execution" class="message-actions">
        <el-button text size="small" :icon="CopyDocument" @click="copyAnswer">复制</el-button>
        <el-button v-if="message.execution" text size="small" :icon="View" @click="emit('execution', message)">
          查看执行过程
        </el-button>
      </div>
    </div>
  </article>
</template>
