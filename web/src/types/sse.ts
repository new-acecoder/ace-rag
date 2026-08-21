import type { PlanStep, Source } from './chat'

export type ChatSseEventName =
  | 'start'
  | 'node_start'
  | 'node_end'
  | 'route'
  | 'plan'
  | 'step'
  | 'tool_start'
  | 'tool_end'
  | 'retrieval'
  | 'rewrite'
  | 'replan'
  | 'token'
  | 'source'
  | 'done'
  | 'error'

export interface SseEnvelope {
  conversationId: string
  turnId: string
  runId: string
  seq: number
}

export interface ChatSseEvent extends SseEnvelope {
  event: ChatSseEventName
  [key: string]: unknown
}

export interface ApiPlanStep {
  step_id: number
  goal: string
  search_query: string
}

export interface ApiSource {
  citation_index: number
  document_id: string
  chunk_id: string
  title: string
  page_number: number | null
  source: string
  document_type: 'txt' | 'md'
}

export interface ApiConversationMessage {
  id: string
  turn_id: string
  role: 'user' | 'assistant'
  content: string
  answer_status?: 'accepted' | 'best_effort'
  sources?: ApiSource[]
}

export interface ApiConversationResponse {
  conversation_id: string
  messages: ApiConversationMessage[]
  active_turn_id: string | null
  resumable_turn_id: string | null
}

export interface ApiSseRecord {
  event: string
  data: Record<string, unknown>
}

export function mapPlanStep(step: ApiPlanStep, status: PlanStep['status'] = 'pending'): PlanStep {
  return {
    stepId: step.step_id,
    goal: step.goal,
    searchQuery: step.search_query,
    status,
  }
}

export function mapSource(source: ApiSource): Source {
  return {
    citationIndex: source.citation_index,
    documentId: source.document_id,
    chunkId: source.chunk_id,
    title: source.title,
    pageNumber: source.page_number,
    source: source.source,
    documentType: source.document_type,
  }
}
