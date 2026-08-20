export interface DocumentItemResponse {
  document_id: string
  title: string
  source: string
  document_type: 'txt' | 'md'
  status: 'ready'
  chunk_count: number
  updated_at: string
}

export interface IngestionJobResponse {
  job_id: string
  document_id: string
  source: string
  document_type: 'txt' | 'md'
  status: 'queued' | 'processing' | 'ready' | 'failed' | 'cancel_requested' | 'cancelled'
  stage: 'parsing' | 'splitting' | 'embedding' | 'indexing' | null
  chunk_count: number | null
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface DocumentItem {
  documentId: string
  title: string
  source: string
  documentType: 'txt' | 'md'
  status: 'ready'
  chunkCount: number
  updatedAt: string
}

export interface IngestionJob {
  jobId: string
  documentId: string
  source: string
  documentType: 'txt' | 'md'
  status: 'queued' | 'processing' | 'ready' | 'failed' | 'cancelRequested' | 'cancelled'
  stage: 'parsing' | 'splitting' | 'embedding' | 'indexing' | null
  chunkCount: number | null
  errorCode: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
}

export interface PendingUpload {
  clientId: string
  fileName: string
  status: 'uploading' | 'failed'
  progress: number | null
  error?: string
}
