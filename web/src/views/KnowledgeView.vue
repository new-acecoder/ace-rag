<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, onUnmounted } from 'vue'

import { getDocumentErrorMessage } from '@/api/document'
import DocumentList from '@/components/knowledge/DocumentList.vue'
import DocumentUpload from '@/components/knowledge/DocumentUpload.vue'
import { useDocumentStore } from '@/stores/document'
import type { DocumentItem } from '@/types/document'

const documentStore = useDocumentStore()

onMounted(() => {
  void documentStore.loadKnowledge()
})

onUnmounted(() => {
  documentStore.stopPolling()
})

async function deleteDocument(document: DocumentItem) {
  try {
    await ElMessageBox.confirm(
      `删除“${document.source}”会同时删除它的全部 ${document.chunkCount} 个分片，且无法恢复。`,
      '确认删除文档',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  try {
    await documentStore.remove(document.documentId)
    ElMessage.success(`“${document.source}”已删除。`)
  } catch (error) {
    await documentStore.loadKnowledge()
    ElMessage.error(getDocumentErrorMessage(error))
  }
}

async function cancelIngestion(jobId: string, source: string) {
  try {
    await ElMessageBox.confirm(`取消“${source}”的处理任务？`, '确认取消任务', {
      confirmButtonText: '取消任务',
      cancelButtonText: '保留任务',
      type: 'warning',
    })
  } catch {
    return
  }

  try {
    await documentStore.cancel(jobId)
    ElMessage.success('已请求取消，后台会清理已生成的数据。')
  } catch (error) {
    await documentStore.loadKnowledge()
    ElMessage.error(getDocumentErrorMessage(error))
  }
}
</script>

<template>
  <div class="knowledge-view">
    <section class="hero">
      <p class="eyebrow">Knowledge</p>
      <h1>把资料放进 Ace RAG</h1>
      <p>上传完成后会在后台解析、分片、向量化并写入知识库。</p>
    </section>

    <DocumentUpload />
    <DocumentList
      :documents="documentStore.documents"
      :pending-uploads="documentStore.pendingUploads"
      :ingestion-jobs="documentStore.ingestionJobs"
      :loading="documentStore.loading"
      :list-error="documentStore.listError"
      @delete="deleteDocument"
      @cancel="cancelIngestion($event.jobId, $event.source)"
      @refresh="documentStore.loadKnowledge"
    />
  </div>
</template>
