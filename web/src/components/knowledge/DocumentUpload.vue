<script setup lang="ts">
import { UploadFilled } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { getDocumentErrorMessage } from '@/api/document'
import { useDocumentStore } from '@/stores/document'

const documentStore = useDocumentStore()
const fileInput = ref<HTMLInputElement>()
const isDragging = ref(false)
const isBusy = computed(() => documentStore.pendingUploads.some((item) => item.status === 'uploading'))

function selectFile() {
  if (!isBusy.value) {
    fileInput.value?.click()
  }
}

async function upload(file: File) {
  const extension = file.name.split('.').pop()?.toLowerCase()
  if (extension !== 'md' && extension !== 'txt') {
    ElMessage.error('当前仅支持 .md 和 .txt 文件。')
    return
  }

  try {
    const job = await documentStore.upload(file)
    ElMessage.success(`“${job.source}” 已提交，正在后台处理。`)
  } catch (error) {
    ElMessage.error(getDocumentErrorMessage(error))
  }
}

function onFileChange(event: Event) {
  const [file] = Array.from((event.target as HTMLInputElement).files ?? [])
  if (file) {
    void upload(file)
  }
  ;(event.target as HTMLInputElement).value = ''
}

function onDrop(event: DragEvent) {
  isDragging.value = false
  const files = Array.from(event.dataTransfer?.files ?? [])
  if (files.length > 1) {
    ElMessage.warning('一次只能上传一个文档。')
  }
  if (files[0] && !isBusy.value) {
    void upload(files[0])
  }
}
</script>

<template>
  <section class="upload-panel">
    <input
      ref="fileInput"
      class="visually-hidden"
      type="file"
      accept=".md,.txt,text/plain,text/markdown"
      @change="onFileChange"
    />
    <div
      class="drop-zone"
      :class="{ 'is-dragging': isDragging, 'is-disabled': isBusy }"
      role="button"
      tabindex="0"
      @click="selectFile"
      @keydown.enter.prevent="selectFile"
      @keydown.space.prevent="selectFile"
      @dragenter.prevent="isDragging = !isBusy"
      @dragover.prevent
      @dragleave.prevent="isDragging = false"
      @drop.prevent="onDrop"
    >
      <el-icon class="upload-icon"><UploadFilled /></el-icon>
      <strong>{{ isBusy ? '正在上传文档…' : '拖拽文件到这里，或点击选择' }}</strong>
      <span>仅支持 Markdown（.md）和纯文本（.txt），一次上传一个文件</span>
    </div>
  </section>
</template>
