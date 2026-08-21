import { http, toApiError, type ApiError } from '@/api/http'
import type { ChatMessage, ConversationHistory, PlanStep, Source } from '@/types/chat'
import {
  mapPlanStep,
  mapSource,
  type ApiConversationResponse,
  type ApiPlanStep,
  type ApiSource,
  type ApiSseRecord,
  type ChatSseEvent,
  type ChatSseEventName,
} from '@/types/sse'
import { consumeSse } from '@/utils/sseParser'

export interface StreamChatRequest {
  conversationId: string
  turnId: string
  message: string
  thinkingEnabled: boolean
}

export class ChatRequestError extends Error {
  constructor(readonly apiError: ApiError) {
    super(apiError.message)
  }
}

export async function streamChat(
  request: StreamChatRequest,
  signal: AbortSignal,
  onEvent: (event: ChatSseEvent) => void,
): Promise<void> {
  return openStream(
    '/api/v1/chat/stream',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: request.conversationId,
        turn_id: request.turnId,
        message: request.message,
        thinking_enabled: request.thinkingEnabled,
      }),
      signal,
    },
    onEvent,
  )
}

export async function resumeChat(
  conversationId: string,
  turnId: string,
  signal: AbortSignal,
  onEvent: (event: ChatSseEvent) => void,
): Promise<void> {
  return openStream(
    `/api/v1/conversations/${conversationId}/turns/${turnId}/resume/stream`,
    { method: 'POST', signal },
    onEvent,
  )
}

export async function getConversation(conversationId: string): Promise<ConversationHistory> {
  try {
    const response = await http.get<ApiConversationResponse>(`/conversations/${conversationId}`)
    return mapConversation(response.data)
  } catch (error) {
    throw new ChatRequestError(toApiError(error))
  }
}

async function openStream(
  path: string,
  init: RequestInit,
  onEvent: (event: ChatSseEvent) => void,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: 'text/event-stream', ...init.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ChatRequestError({ code: 'NETWORK_ERROR', message: '无法连接到服务，请确认后端已启动。' })
  }

  if (!response.ok) {
    let apiError: ApiError = { code: 'NETWORK_ERROR', message: '请求 Chat 服务失败。' }
    try {
      apiError = (await response.json()) as ApiError
    } catch {
      // 后端安全错误体不可用时保留通用提示。
    }
    throw new ChatRequestError(apiError)
  }
  await consumeSse(response, (record) => onEvent(mapSseEvent(record)))
}

function mapConversation(response: ApiConversationResponse): ConversationHistory {
  return {
    conversationId: response.conversation_id,
    messages: response.messages.map((message): ChatMessage => ({
      id: message.id,
      conversationId: response.conversation_id,
      turnId: message.turn_id,
      runId: null,
      role: message.role,
      content: message.content,
      status: 'done',
      answerStatus: message.answer_status,
      sources: message.sources?.map(mapSource),
    })),
    activeTurnId: response.active_turn_id,
    resumableTurnId: response.resumable_turn_id,
  }
}

function mapSseEvent(record: ApiSseRecord): ChatSseEvent {
  const event = record.event as ChatSseEventName
  const data = record.data
  const base = {
    event,
    conversationId: requiredString(data, 'conversation_id'),
    turnId: requiredString(data, 'turn_id'),
    runId: requiredString(data, 'run_id'),
    seq: requiredNumber(data, 'seq'),
  }

  switch (event) {
    case 'plan':
      return { ...base, steps: asArray<ApiPlanStep>(data.steps).map((step) => mapPlanStep(step)) }
    case 'step':
      return {
        ...base,
        stepId: requiredNumber(data, 'step_id'),
        goal: requiredString(data, 'goal'),
        searchQuery: requiredString(data, 'search_query'),
        status: requiredString(data, 'status'),
        completed: requiredNumber(data, 'completed'),
        total: requiredNumber(data, 'total'),
      }
    case 'source':
      return { ...base, source: mapSource(data as unknown as ApiSource) }
    case 'node_start':
      return { ...base, node: requiredString(data, 'node') }
    case 'node_end':
      return {
        ...base,
        node: requiredString(data, 'node'),
        status: requiredString(data, 'status'),
        durationMs: requiredNumber(data, 'duration_ms'),
        result: asRecord(data.result),
      }
    case 'route':
      return {
        ...base,
        routeType: requiredString(data, 'route_type'),
        requiredCapabilities: asArray<string>(data.required_capabilities),
        reason: requiredString(data, 'reason'),
      }
    case 'retrieval':
      return {
        ...base,
        query: requiredString(data, 'query'),
        resultCount: requiredNumber(data, 'result_count'),
        relevantCount: requiredNumber(data, 'relevant_count'),
        round: typeof data.round === 'number' ? data.round : undefined,
        strategy: typeof data.strategy === 'string' ? data.strategy : undefined,
        queries: asArray<string>(data.queries),
      }
    case 'rewrite':
      return {
        ...base,
        previousQuery: requiredString(data, 'previous_query'),
        rewrittenQuery: requiredString(data, 'rewritten_query'),
        missingAspects: asArray<string>(data.missing_aspects),
      }
    case 'replan':
      return {
        ...base,
        action: requiredString(data, 'action'),
        remainingSteps: asArray<ApiPlanStep>(data.remaining_steps).map((step) => mapPlanStep(step)),
        reason: requiredString(data, 'reason'),
      }
    case 'tool_start':
      return {
        ...base,
        toolCallId: requiredString(data, 'tool_call_id'),
        toolName: requiredString(data, 'tool_name'),
        args: asRecord(data.args) ?? {},
      }
    case 'tool_end':
      return {
        ...base,
        toolCallId: requiredString(data, 'tool_call_id'),
        toolName: requiredString(data, 'tool_name'),
        success: Boolean(data.success),
        resultCount: requiredNumber(data, 'result_count'),
      }
    case 'token':
      return { ...base, content: requiredString(data, 'content') }
    case 'done':
      return {
        ...base,
        messageId: requiredString(data, 'message_id'),
        answerStatus: requiredString(data, 'answer_status'),
      }
    case 'error':
      return {
        ...base,
        code: requiredString(data, 'code'),
        message: requiredString(data, 'message'),
        resumable: Boolean(data.resumable),
      }
    case 'start':
      return { ...base, resumed: Boolean(data.resumed) }
    default:
      throw new Error(`未知 SSE Event：${record.event}`)
  }
}

function requiredString(value: Record<string, unknown>, key: string): string {
  const result = value[key]
  if (typeof result !== 'string') throw new Error(`SSE 缺少 ${key}。`)
  return result
}

function requiredNumber(value: Record<string, unknown>, key: string): number {
  const result = value[key]
  if (typeof result !== 'number') throw new Error(`SSE 缺少 ${key}。`)
  return result
}

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined
}

export type { PlanStep, Source }
