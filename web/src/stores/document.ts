import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  cancelIngestionJob,
  deleteDocument,
  getDocumentErrorMessage,
  getIngestionJob,
  listDocuments,
  listIngestionJobs,
  uploadDocument,
} from '@/api/document'
import type { DocumentItem, IngestionJob, PendingUpload } from '@/types/document'

const pollingStatuses = new Set<IngestionJob['status']>([
  'queued',
  'processing',
  'cancelRequested',
])

export const useDocumentStore = defineStore('document', () => {
  const documents = ref<DocumentItem[]>([])
  const pendingUploads = ref<PendingUpload[]>([])
  const ingestionJobs = ref<IngestionJob[]>([])
  const loading = ref(false)
  const listError = ref<string | null>(null)
  let pollingTimer: ReturnType<typeof setInterval> | undefined
  let polling = false

  function sortDocuments(items: DocumentItem[]) {
    return [...items].sort(
      (left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt),
    )
  }

  function sortJobs(items: IngestionJob[]) {
    return [...items].sort(
      (left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt),
    )
  }

  function mergeJob(job: IngestionJob) {
    const items = new Map(ingestionJobs.value.map((item) => [item.jobId, item]))
    items.set(job.jobId, job)
    ingestionJobs.value = sortJobs([...items.values()])
  }

  function activeJobs() {
    return ingestionJobs.value.filter((job) => pollingStatuses.has(job.status))
  }

  function ensurePolling() {
    if (activeJobs().length === 0) {
      stopPolling()
      return
    }
    if (!pollingTimer) {
      pollingTimer = setInterval(() => void refreshActiveJobs(), 2_000)
    }
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer)
      pollingTimer = undefined
    }
  }

  async function loadDocuments(): Promise<void> {
    documents.value = sortDocuments(await listDocuments())
  }

  async function loadKnowledge(): Promise<void> {
    loading.value = true
    listError.value = null
    try {
      const [loadedDocuments, loadedJobs] = await Promise.all([listDocuments(), listIngestionJobs()])
      documents.value = sortDocuments(loadedDocuments)
      ingestionJobs.value = sortJobs(loadedJobs)
    } catch (error) {
      listError.value = getDocumentErrorMessage(error)
    } finally {
      loading.value = false
      ensurePolling()
    }
  }

  async function refreshActiveJobs(): Promise<void> {
    if (polling) return
    const jobs = activeJobs()
    if (jobs.length === 0) {
      stopPolling()
      return
    }

    polling = true
    try {
      const updates = await Promise.all(jobs.map((job) => getIngestionJob(job.jobId)))
      let shouldRefreshDocuments = false
      for (const job of updates) {
        if (job.status === 'ready') {
          ingestionJobs.value = ingestionJobs.value.filter((item) => item.jobId !== job.jobId)
          shouldRefreshDocuments = true
        } else if (job.status === 'cancelled') {
          ingestionJobs.value = ingestionJobs.value.filter((item) => item.jobId !== job.jobId)
        } else {
          mergeJob(job)
        }
      }
      if (shouldRefreshDocuments) {
        await loadDocuments()
      }
      listError.value = null
    } catch (error) {
      listError.value = getDocumentErrorMessage(error)
    } finally {
      polling = false
      ensurePolling()
    }
  }

  async function upload(file: File): Promise<IngestionJob> {
    const clientId = crypto.randomUUID()
    const pending: PendingUpload = {
      clientId,
      fileName: file.name,
      status: 'uploading',
      progress: 0,
    }
    pendingUploads.value.unshift(pending)

    try {
      const job = await uploadDocument(file, ({ percent }) => {
        const current = pendingUploads.value.find((item) => item.clientId === clientId)
        if (current) current.progress = percent
      })
      pendingUploads.value = pendingUploads.value.filter((item) => item.clientId !== clientId)
      mergeJob(job)
      ensurePolling()
      return job
    } catch (error) {
      const current = pendingUploads.value.find((item) => item.clientId === clientId)
      if (current) {
        current.status = 'failed'
        current.error = getDocumentErrorMessage(error)
      }
      throw error
    }
  }

  async function cancel(jobId: string): Promise<void> {
    mergeJob(await cancelIngestionJob(jobId))
    ensurePolling()
  }

  async function remove(documentId: string): Promise<void> {
    await deleteDocument(documentId)
    documents.value = documents.value.filter((item) => item.documentId !== documentId)
  }

  return {
    documents,
    pendingUploads,
    ingestionJobs,
    loading,
    listError,
    loadKnowledge,
    upload,
    cancel,
    remove,
    stopPolling,
  }
})
