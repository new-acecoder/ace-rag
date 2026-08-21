<script setup lang="ts">
import { Promotion, VideoPause } from '@element-plus/icons-vue'
import { ref } from 'vue'

defineProps<{
  disabled: boolean
  streaming: boolean
  thinkingEnabled: boolean
}>()

const emit = defineEmits<{
  submit: [content: string]
  stop: []
  'update:thinkingEnabled': [value: boolean]
}>()

const value = ref('')

function submit(): void {
  const content = value.value.trim()
  if (!content) return
  emit('submit', content)
  value.value = ''
}

</script>

<template>
  <div class="chat-composer">
    <div class="composer-box">
      <el-input
        v-model="value"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 5 }"
        :disabled="disabled"
        placeholder="输入你的问题…"
        @keydown.enter.exact.prevent="submit"
      />
      <el-button
        v-if="streaming"
        circle
        type="warning"
        :icon="VideoPause"
        aria-label="停止生成"
        @click="emit('stop')"
      />
      <el-button
        v-else
        circle
        type="primary"
        :icon="Promotion"
        :disabled="disabled || !value.trim()"
        aria-label="发送"
        @click="submit"
      />
    </div>
    <div class="composer-options">
      <span>深度思考</span>
      <el-switch
        :model-value="thinkingEnabled"
        :disabled="streaming"
        @update:model-value="emit('update:thinkingEnabled', $event)"
      />
    </div>
    <p>Enter 发送，Shift + Enter 换行。回答只基于已入库知识库内容。</p>
  </div>
</template>
