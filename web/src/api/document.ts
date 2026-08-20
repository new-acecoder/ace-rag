import { http, toApiError } from './http'
import type {
  DocumentItem,
  DocumentItemResponse,
  IngestionJob,
  IngestionJobResponse,
} from '@/types/document'

export interface UploadProgress {
  percent: number | null
}

export async function uploadDocument(
  file: File,
  onProgress: (progress: UploadProgress) => void,
): Promise<IngestionJob> {
  const formData = new FormData()
  formData.append('file', file)

  try {
    const response = await http.post<IngestionJobResponse>('/documents', formData, {
      onUploadProgress(event) {
        const percent = event.total
          ? Math.min(100, Math.round((event.loaded / event.total) * 100))
          : null
        onProgress({ percent })
      },
    })
    return toIngestionJob(response.data)
  } catch (error) {
    throw toApiError(error)
  }
}

export async function listDocuments(): Promise<DocumentItem[]> {
  try {
    const response = await http.get<DocumentItemResponse[]>('/documents')
    return response.data.map(toDocumentItem)
  } catch (error) {
    throw toApiError(error)
  }
}

export async function deleteDocument(documentId: string): Promise<void> {
  try {
    await http.delete(`/documents/${documentId}`)
  } catch (error) {
    throw toApiError(error)
  }
}

export async function listIngestionJobs(): Promise<IngestionJob[]> {
  try {
    const response = await http.get<IngestionJobResponse[]>('/document-ingestions')
    return response.data.map(toIngestionJob)
  } catch (error) {
    throw toApiError(error)
  }
}

export async function getIngestionJob(jobId: string): Promise<IngestionJob> {
  try {
    const response = await http.get<IngestionJobResponse>(`/document-ingestions/${jobId}`)
    return toIngestionJob(response.data)
  } catch (error) {
    throw toApiError(error)
  }
}

export async function cancelIngestionJob(jobId: string): Promise<IngestionJob> {
  try {
    const response = await http.post<IngestionJobResponse>(`/document-ingestions/${jobId}/cancel`)
    return toIngestionJob(response.data)
  } catch (error) {
    throw toApiError(error)
  }
}

function toDocumentItem(response: DocumentItemResponse): DocumentItem {
  return {
    documentId: response.document_id,
    title: response.title,
    source: response.source,
    documentType: response.document_type,
    status: response.status,
    chunkCount: response.chunk_count,
    updatedAt: response.updated_at,
  }
}

function toIngestionJob(response: IngestionJobResponse): IngestionJob {
  return {
    jobId: response.job_id,
    documentId: response.document_id,
    source: response.source,
    documentType: response.document_type,
    status: response.status === 'cancel_requested' ? 'cancelRequested' : response.status,
    stage: response.stage,
    chunkCount: response.chunk_count,
    errorCode: response.error_code,
    errorMessage: response.error_message,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
  }
}

export function getDocumentErrorMessage(error: unknown): string {
  const messages: Record<string, string> = {
    DOCUMENT_TOO_LARGE: '文件大小超过服务端限制。',
    UNSUPPORTED_DOCUMENT_TYPE: '当前仅支持 .md 和 .txt 文件。',
    DOCUMENT_NOT_FOUND: '文档不存在，列表将刷新。',
    INGESTION_JOB_NOT_FOUND: '摄取任务不存在，列表将刷新。',
    INGESTION_JOB_NOT_CANCELLABLE: '当前任务已结束，无法取消。',
    SERVICE_UNAVAILABLE: '依赖服务暂不可用，请稍后重试。',
  }

  if (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    'message' in error &&
    typeof error.code === 'string' &&
    typeof error.message === 'string'
  ) {
    return messages[error.code] ?? error.message
  }

  return '请求失败，请稍后重试。'
}
