<script setup lang="ts">
import type { Source } from '@/types/chat'

defineProps<{
  open: boolean
  source: Source | null
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()
</script>

<template>
  <el-drawer :model-value="open" title="参考来源" size="360px" @update:model-value="emit('update:open', $event)">
    <template v-if="source">
      <p class="drawer-citation">[{{ source.citationIndex }}]</p>
      <h3>{{ source.title }}</h3>
      <dl class="source-details">
        <div><dt>文件</dt><dd>{{ source.source }}</dd></div>
        <div><dt>类型</dt><dd>{{ source.documentType.toUpperCase() }}</dd></div>
        <div v-if="source.pageNumber !== null"><dt>页码</dt><dd>P{{ source.pageNumber }}</dd></div>
        <div><dt>Chunk</dt><dd>{{ source.chunkId }}</dd></div>
      </dl>
    </template>
  </el-drawer>
</template>
