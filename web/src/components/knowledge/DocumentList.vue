<script setup lang="ts">
import { Delete, Refresh } from '@element-plus/icons-vue'
import { computed } from 'vue'

import type { DocumentItem, IngestionJob, PendingUpload } from '@/types/document'

const props = defineProps<{
  documents: DocumentItem[]
  pendingUploads: PendingUpload[]
  ingestionJobs: IngestionJob[]
  loading: boolean
  listError: string | null
}>()

const emit = defineEmits<{
  delete: [document: DocumentItem]
  cancel: [job: IngestionJob]
  refresh: []
}>()

const uploadRows = computed(() => props.pendingUploads.map((item) => ({
  key: item.clientId,
  name: item.fileName,
  documentType: item.fileName.split('.').pop()?.toUpperCase() ?? '未知',
  status: item.status,
  progress: item.progress,
  error: item.error,
})))

function pendingStatusLabel(status: 'uploading' | 'failed') {
  return status === 'uploading' ? '上传中' : '失败'
}

function pendingStatusType(status: 'uploading' | 'failed') {
  return status === 'uploading' ? 'warning' : 'danger'
}

function jobStatusLabel(job: IngestionJob) {
  if (job.status === 'queued') return '排队中'
  if (job.status === 'cancelRequested') return '正在取消'
  if (job.status === 'failed') return '失败'
  if (job.status === 'ready') return '已完成'
  if (job.status === 'cancelled') return '已取消'

  return {
    parsing: '正在解析',
    splitting: '正在分片',
    embedding: '正在向量化',
    indexing: '正在索引',
  }[job.stage ?? 'parsing']
}

function jobStatusType(job: IngestionJob) {
  if (job.status === 'failed') return 'danger'
  if (job.status === 'ready') return 'success'
  if (job.status === 'cancelled') return 'info'
  return 'warning'
}

function canCancel(job: IngestionJob) {
  return job.status === 'queued' || job.status === 'processing'
}

function formatUpdatedAt(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}
</script>

<template>
  <section class="document-list" aria-labelledby="document-list-title">
    <div class="section-title">
      <div>
        <h2 id="document-list-title">已入库文档</h2>
        <p>这里展示已完成入库、可以被检索的文档。</p>
      </div>
      <el-button text :icon="Refresh" :loading="loading" @click="emit('refresh')">刷新</el-button>
    </div>

    <el-alert v-if="listError" class="list-error" type="error" :closable="false" show-icon>
      <template #title>{{ listError }}</template>
    </el-alert>
    <el-skeleton v-else-if="loading && documents.length === 0" class="document-skeleton" animated :rows="3" />
    <el-empty v-else-if="documents.length === 0" description="还没有已入库文档" :image-size="82" />
    <el-table v-else :data="documents" class="document-table" :show-header="true">
      <el-table-column prop="source" label="文件名" min-width="220" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ row.documentType.toUpperCase() }}</template>
      </el-table-column>
      <el-table-column label="状态" width="105">
        <template #default><el-tag type="success" effect="light">已完成</el-tag></template>
      </el-table-column>
      <el-table-column prop="chunkCount" label="分片数" width="100" />
      <el-table-column label="更新时间" min-width="170">
        <template #default="{ row }">{{ formatUpdatedAt(row.updatedAt) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="86" fixed="right">
        <template #default="{ row }">
          <el-button text type="danger" :icon="Delete" @click="emit('delete', row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>

  <section v-if="ingestionJobs.length > 0" class="pending-upload-list" aria-labelledby="ingestion-job-title">
    <div class="section-title">
      <div>
        <h2 id="ingestion-job-title">文档处理任务</h2>
        <p>这些任务保存在服务端；刷新页面后会继续显示。</p>
      </div>
    </div>
    <el-table :data="ingestionJobs" class="document-table" :show-header="true">
      <el-table-column prop="source" label="文件名" min-width="220" />
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ row.documentType.toUpperCase() }}</template>
      </el-table-column>
      <el-table-column label="状态" min-width="160">
        <template #default="{ row }">
          <el-tag :type="jobStatusType(row)" effect="light">{{ jobStatusLabel(row) }}</el-tag>
          <span v-if="row.status === 'failed'" class="error-text">{{ row.errorMessage }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="170">
        <template #default="{ row }">{{ formatUpdatedAt(row.updatedAt) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="86" fixed="right">
        <template #default="{ row }">
          <el-button v-if="canCancel(row)" text type="warning" @click="emit('cancel', row)">取消</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>

  <section v-if="uploadRows.length > 0" class="pending-upload-list" aria-labelledby="pending-upload-title">
    <div class="section-title">
      <div>
        <h2 id="pending-upload-title">当前上传</h2>
        <p>文件传输完成前，这些状态仅保存在当前页面。</p>
      </div>
    </div>
    <el-table :data="uploadRows" class="document-table" :show-header="true">
      <el-table-column prop="name" label="文件名" min-width="240" />
      <el-table-column prop="documentType" label="类型" width="90" />
      <el-table-column label="状态" min-width="180">
        <template #default="{ row }">
          <el-tag :type="pendingStatusType(row.status)" effect="light">
            {{ pendingStatusLabel(row.status) }}
          </el-tag>
          <span v-if="row.status === 'uploading' && row.progress !== null" class="progress-text">
            {{ row.progress }}%
          </span>
          <span v-if="row.status === 'failed'" class="error-text">{{ row.error }}</span>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>
