export interface Source {
  citationIndex: number
  documentId: string
  chunkId: string
  title: string
  pageNumber: number | null
  source: string
  documentType: 'txt' | 'md'
}

export type ChatMessageStatus = 'streaming' | 'stopping' | 'done' | 'stopped' | 'error'

export interface PlanStep {
  stepId: number
  goal: string
  searchQuery: string
  status: 'pending' | 'running' | 'completed' | 'not_run'
}

export interface ExecutionNode {
  id: string
  node: string
  status: 'running' | 'succeeded' | 'failed'
  seq: number
  durationMs?: number
  result?: Record<string, unknown>
}

export type ExecutionTraceType =
  | 'route'
  | 'node'
  | 'tool'
  | 'retrieval'
  | 'rewrite'
  | 'plan'
  | 'evaluation'

export interface ExecutionTraceItem {
  id: string
  seq: number
  type: ExecutionTraceType
  label: string
  detail?: string
  status: 'running' | 'succeeded' | 'failed'
  durationMs?: number
  round?: number
  groupId?: string
  groupLabel?: string
}

export interface ExecutionInfo {
  conversationId: string
  turnId: string
  runId: string
  lastSeq: number
  route?: 'general_chat' | 'react' | 'plan_execute'
  requiredCapabilities?: string[]
  routeReason?: string
  nodes: ExecutionNode[]
  trace: ExecutionTraceItem[]
  plan?: PlanStep[]
  latestActivity?: string
}

export interface ChatMessage {
  id: string
  conversationId: string
  turnId: string
  runId: string | null
  role: 'user' | 'assistant'
  content: string
  status: ChatMessageStatus
  answerStatus?: 'accepted' | 'best_effort'
  sources?: Source[]
  execution?: ExecutionInfo
}

export interface Conversation {
  conversationId: string
  title: string
  updatedAt: string
}

export interface ConversationHistory {
  conversationId: string
  messages: ChatMessage[]
  activeTurnId: string | null
  resumableTurnId: string | null
}
