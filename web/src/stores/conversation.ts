import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import {
  ChatRequestError,
  getConversation,
  resumeChat,
  streamChat,
} from '@/api/chat'
import type {
  ChatMessage,
  Conversation,
  ConversationHistory,
  ExecutionInfo,
  ExecutionNode,
  ExecutionTraceItem,
  PlanStep,
  Source,
} from '@/types/chat'
import type { ChatSseEvent } from '@/types/sse'

const STORAGE_KEY = 'ace-rag:conversations'
const THINKING_STORAGE_KEY = 'ace-rag:thinking-enabled'
const reconcileDelays = [0, 350, 700, 1_050]

export const useConversationStore = defineStore('conversation', () => {
  const conversations = ref<Conversation[]>(readConversations())
  const currentConversationId = ref<string | null>(conversations.value[0]?.conversationId ?? null)
  const messages = ref<ChatMessage[]>([])
  const streaming = ref(false)
  const activeTurnId = ref<string | null>(null)
  const activeRunId = ref<string | null>(null)
  const currentStatus = ref<string | null>(null)
  const execution = ref<ExecutionInfo | null>(null)
  const resumableTurnId = ref<string | null>(null)
  const abortController = ref<AbortController | null>(null)
  const loadingHistory = ref(false)
  const error = ref<string | null>(null)
  const thinkingEnabled = ref(readThinkingEnabled())
  const toolStartedAt = new Map<string, number>()

  const canSend = computed(
    () => Boolean(currentConversationId.value) && !streaming.value && !activeTurnId.value && !resumableTurnId.value,
  )

  async function initialize(): Promise<void> {
    if (!currentConversationId.value) {
      createConversation()
      return
    }
    await selectConversation(currentConversationId.value)
  }

  function createConversation(): string {
    if (streaming.value) void stopChat()
    const conversationId = crypto.randomUUID()
    const conversation = {
      conversationId,
      title: '新对话',
      updatedAt: new Date().toISOString(),
    }
    conversations.value = [conversation, ...conversations.value]
    saveConversations()
    currentConversationId.value = conversationId
    messages.value = []
    activeTurnId.value = null
    activeRunId.value = null
    resumableTurnId.value = null
    execution.value = null
    currentStatus.value = null
    error.value = null
    return conversationId
  }

  async function selectConversation(conversationId: string): Promise<void> {
    if (streaming.value && currentConversationId.value !== conversationId) await stopChat()
    currentConversationId.value = conversationId
    execution.value = null
    await refreshConversation(conversationId)
  }

  async function refreshConversation(conversationId = currentConversationId.value): Promise<void> {
    if (!conversationId) return
    loadingHistory.value = true
    error.value = null
    try {
      const history = await getConversation(conversationId)
      if (currentConversationId.value !== conversationId) return
      applyHistory(history)
    } catch (caught) {
      const requestError = toChatRequestError(caught)
      if (requestError.apiError.code === 'CONVERSATION_NOT_FOUND') {
        removeConversation(conversationId)
      } else {
        error.value = requestError.apiError.message
      }
    } finally {
      loadingHistory.value = false
    }
  }

  async function sendMessage(content: string): Promise<void> {
    const message = content.trim()
    const conversationId = currentConversationId.value ?? createConversation()
    if (!message || !canSend.value) return

    const turnId = crypto.randomUUID()
    const controller = new AbortController()
    const started = startAttempt(conversationId, turnId, controller, message)
    updateConversationTitle(conversationId, message)

    try {
      await streamChat(
        { conversationId, turnId, message, thinkingEnabled: thinkingEnabled.value },
        controller.signal,
        consumeEvent,
      )
      if (!started.terminal) await reconcileTurn(conversationId, turnId)
    } catch (caught) {
      if (isAbortError(caught)) {
        await reconcileTurn(conversationId, turnId)
      } else {
        await handleStreamFailure(caught, conversationId, turnId)
      }
    } finally {
      if (abortController.value === controller) abortController.value = null
      streaming.value = false
    }
  }

  async function resumeTurn(turnId = resumableTurnId.value): Promise<void> {
    const conversationId = currentConversationId.value
    if (!conversationId || !turnId || streaming.value || activeTurnId.value) return

    const controller = new AbortController()
    const started = startAttempt(conversationId, turnId, controller)
    try {
      await resumeChat(conversationId, turnId, controller.signal, consumeEvent)
      if (!started.terminal) await reconcileTurn(conversationId, turnId)
    } catch (caught) {
      if (isAbortError(caught)) {
        await reconcileTurn(conversationId, turnId)
      } else {
        await handleStreamFailure(caught, conversationId, turnId)
      }
    } finally {
      if (abortController.value === controller) abortController.value = null
      streaming.value = false
    }
  }

  async function stopChat(): Promise<void> {
    const turnId = activeTurnId.value
    const conversationId = currentConversationId.value
    if (!turnId || !conversationId) return
    const assistant = assistantMessage(turnId)
    if (assistant) assistant.status = 'stopping'
    currentStatus.value = '正在停止并确认执行状态…'
    abortController.value?.abort()
  }

  function setThinkingEnabled(value: boolean): void {
    thinkingEnabled.value = value
    localStorage.setItem(THINKING_STORAGE_KEY, JSON.stringify(value))
  }

  async function reconcileTurn(conversationId: string, turnId: string): Promise<void> {
    for (const delay of reconcileDelays) {
      if (delay) await wait(delay)
      try {
        const history = await getConversation(conversationId)
        if (currentConversationId.value !== conversationId) return
        applyHistory(history)
        const finalAssistant = messages.value.find((message) => message.id === `${turnId}:assistant` && message.status === 'done')
        if (finalAssistant) {
          finishAttempt(turnId)
          return
        }
        if (history.activeTurnId === turnId) {
          currentStatus.value = '正在停止并确认执行状态…'
          continue
        }
        if (history.resumableTurnId === turnId) {
          const assistant = assistantMessage(turnId)
          if (assistant) assistant.status = 'stopped'
          activeTurnId.value = null
          activeRunId.value = null
          resumableTurnId.value = turnId
          currentStatus.value = '执行已停止，可继续执行。'
          return
        }
        markAttemptError(turnId, '连接已中断，请刷新会话状态。')
        return
      } catch {
        // 保留本地停止状态，下一次手动刷新可继续对账。
      }
    }
    currentStatus.value = '执行状态暂未确认，请刷新会话。'
  }

  function consumeEvent(event: ChatSseEvent): void {
    const conversationId = currentConversationId.value
    if (event.event === 'start') {
      if (conversationId !== event.conversationId || activeTurnId.value !== event.turnId) return
      bindRun(event)
      return
    }
    if (
      conversationId !== event.conversationId ||
      activeTurnId.value !== event.turnId ||
      activeRunId.value !== event.runId ||
      !execution.value ||
      event.seq <= execution.value.lastSeq
    ) return

    execution.value.lastSeq = event.seq
    const assistant = assistantMessage(event.turnId)
    if (!assistant) return

    switch (event.event) {
      case 'node_start':
        startNode(event.node as string, event.seq)
        currentStatus.value = activityForNode(event.node as string)
        break
      case 'node_end':
        finishNode(
          event.node as string,
          event.status === 'failed' ? 'failed' : 'succeeded',
          event.durationMs as number,
          event.result as Record<string, unknown> | undefined,
          event.seq,
        )
        break
      case 'route':
        execution.value.route = event.routeType as ExecutionInfo['route']
        execution.value.requiredCapabilities = event.requiredCapabilities as string[]
        execution.value.routeReason = event.reason as string
        recordRoute(event)
        break
      case 'plan':
        execution.value.plan = event.steps as PlanStep[]
        recordPlan(event)
        break
      case 'step':
        updatePlanStep(event)
        recordPlanStep(event)
        currentStatus.value = `正在执行 ${event.completed as number} / ${event.total as number} 个任务…`
        break
      case 'retrieval':
        recordRetrieval(event)
        currentStatus.value = `已检索 ${event.resultCount as number} 条，其中 ${event.relevantCount as number} 条可用。`
        break
      case 'rewrite':
        recordRewrite(event)
        currentStatus.value = '正在优化检索问题…'
        break
      case 'replan':
        applyReplan(event)
        recordReplan(event)
        currentStatus.value = event.action === 'revise' ? '计划已调整，继续收集证据…' : '正在整理已收集的证据…'
        break
      case 'tool_start':
        startTool(event)
        currentStatus.value = `正在调用 ${(event.toolName as string) || '知识库工具'}…`
        break
      case 'tool_end':
        finishTool(event)
        break
      case 'token':
        assistant.content += event.content as string
        assistant.status = 'streaming'
        currentStatus.value = '正在生成已评估的最终回答…'
        break
      case 'source':
        assistant.sources = [...(assistant.sources ?? []), event.source as Source]
        break
      case 'done':
        if (event.messageId !== assistant.id) return
        assistant.answerStatus = event.answerStatus as ChatMessage['answerStatus']
        assistant.status = 'done'
        if (assistant.answerStatus === 'best_effort') markNotRunSteps(execution.value)
        assistant.execution = execution.value
        currentStatus.value = null
        break
      case 'error':
        assistant.status = 'error'
        failRunningTrace(event.message as string)
        currentStatus.value = event.resumable ? '正在确认是否可以继续执行…' : (event.message as string)
        error.value = event.message as string
        break
    }
  }

  function bindRun(event: ChatSseEvent): void {
    activeRunId.value = event.runId
    toolStartedAt.clear()
    const assistant = assistantMessage(event.turnId)
    if (!assistant) return
    assistant.runId = event.runId
    assistant.status = 'streaming'
    assistant.content = ''
    assistant.sources = []
    execution.value = {
      conversationId: event.conversationId,
      turnId: event.turnId,
      runId: event.runId,
      lastSeq: event.seq,
      nodes: [],
      trace: [],
      latestActivity: event.resumed ? '已恢复执行…' : '正在分析问题…',
    }
    assistant.execution = execution.value
    currentStatus.value = execution.value.latestActivity ?? null
  }

  function startAttempt(
    conversationId: string,
    turnId: string,
    controller: AbortController,
    userContent?: string,
  ): { terminal: boolean } {
    if (userContent) {
      messages.value.push({
        id: `${turnId}:user`,
        conversationId,
        turnId,
        runId: null,
        role: 'user',
        content: userContent,
        status: 'done',
      })
    }
    let assistant = assistantMessage(turnId)
    if (!assistant) {
      assistant = {
        id: `${turnId}:assistant`,
        conversationId,
        turnId,
        runId: null,
        role: 'assistant',
        content: '',
        status: 'streaming',
        sources: [],
      }
      messages.value.push(assistant)
    }
    assistant.status = 'streaming'
    assistant.execution = undefined
    activeTurnId.value = turnId
    activeRunId.value = null
    resumableTurnId.value = null
    abortController.value = controller
    streaming.value = true
    error.value = null
    currentStatus.value = '正在连接 Agent…'
    return { terminal: false }
  }

  async function handleStreamFailure(
    caught: unknown,
    conversationId: string,
    turnId: string,
  ): Promise<void> {
    const requestError = toChatRequestError(caught)
    if (requestError.apiError.code === 'CONVERSATION_NOT_FOUND') {
      removeConversation(conversationId)
      return
    }
    if (['CONVERSATION_BUSY', 'TURN_REQUIRES_RESUME', 'TURN_ALREADY_COMPLETED'].includes(requestError.apiError.code)) {
      currentStatus.value = requestError.apiError.message
      await refreshConversation(conversationId)
      return
    }
    markAttemptError(turnId, requestError.apiError.message)
    await reconcileTurn(conversationId, turnId)
  }

  function applyHistory(history: ConversationHistory): void {
    const prior = new Map(messages.value.map((message) => [message.id, message]))
    messages.value = history.messages.map((message) => ({
      ...message,
      execution: prior.get(message.id)?.execution,
    }))
    activeTurnId.value = history.activeTurnId
    resumableTurnId.value = history.resumableTurnId

    if (history.activeTurnId && !assistantMessage(history.activeTurnId)) {
      messages.value.push(placeholder(history.conversationId, history.activeTurnId, 'stopping'))
    }
    if (history.resumableTurnId && !assistantMessage(history.resumableTurnId)) {
      messages.value.push(placeholder(history.conversationId, history.resumableTurnId, 'stopped'))
    }
    if (!history.activeTurnId) activeRunId.value = null
  }

  function finishAttempt(turnId: string): void {
    if (activeTurnId.value !== turnId) return
    const assistant = assistantMessage(turnId)
    if (assistant && execution.value) assistant.execution = execution.value
    activeTurnId.value = null
    activeRunId.value = null
    resumableTurnId.value = null
    currentStatus.value = null
  }

  function markAttemptError(turnId: string, message: string): void {
    const assistant = assistantMessage(turnId)
    if (assistant) {
      assistant.status = 'error'
      if (execution.value) assistant.execution = execution.value
    }
    currentStatus.value = message
    error.value = message
  }

  function startNode(node: string, seq: number): void {
    const current = execution.value
    if (!current) return
    const id = `${current.runId}:node:${seq}`
    current.nodes.push({ id, node, status: 'running', seq })
    current.trace.push({
      id,
      seq,
      type: isEvaluationNode(node) ? 'evaluation' : 'node',
      label: nodeTraceLabel(node),
      status: 'running',
      ...activeTraceGroup(current),
    })
  }

  function finishNode(
    node: string,
    status: ExecutionNode['status'],
    durationMs: number,
    result: Record<string, unknown> | undefined,
    seq: number,
  ): void {
    const current = execution.value
    if (!current) return
    const existing = [...current.nodes]
      .reverse()
      .find((item) => item.node === node && item.status === 'running')
    const detail = nodeResultDetail(node, result)
    if (!existing) {
      const id = `${current.runId}:node:${seq}`
      current.nodes.push({ id, node, status, seq, durationMs, ...(result ? { result } : {}) })
      current.trace.push({
        id,
        seq,
        type: isEvaluationNode(node) ? 'evaluation' : 'node',
        label: nodeTraceLabel(node),
        status,
        durationMs,
        ...(detail ? { detail } : {}),
        ...activeTraceGroup(current),
      })
      return
    }
    existing.status = status
    existing.durationMs = durationMs
    if (result) existing.result = result
    const trace = current.trace.find((item) => item.id === existing.id)
    if (trace) {
      trace.status = status
      trace.durationMs = durationMs
      if (detail) trace.detail = detail
    }
  }

  function recordRoute(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const capabilities = (event.requiredCapabilities as string[])
      .map(capabilityLabel)
      .filter(Boolean)
    const reason = event.reason as string
    const detail = [reason, capabilities.length ? `所需能力：${capabilities.join('、')}` : '无需工具']
      .filter(Boolean)
      .join(' · ')
    current.trace.push({
      id: `${current.runId}:route:${event.seq}`,
      seq: event.seq,
      type: 'route',
      label: routeTraceLabel(event.routeType as string),
      detail,
      status: 'succeeded',
    })
  }

  function recordPlan(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const steps = event.steps as PlanStep[]
    current.trace.push({
      id: `${current.runId}:plan:${event.seq}`,
      seq: event.seq,
      type: 'plan',
      label: `已生成 ${steps.length} 个检索任务`,
      detail: steps.map((step) => `${step.stepId}. ${step.goal}`).join('；'),
      status: 'succeeded',
    })
  }

  function recordPlanStep(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const stepId = event.stepId as number
    const groupId = `plan:${stepId}`
    const groupLabel = `任务 ${stepId} · ${event.goal as string}`
    if (event.status === 'completed') {
      const trace = [...current.trace]
        .reverse()
        .find((item) => item.type === 'plan' && item.groupId === groupId && item.status === 'running')
      if (trace) {
        trace.status = 'succeeded'
        trace.detail = `已完成 ${event.completed as number} / ${event.total as number} 个任务`
        return
      }
    }
    current.trace.push({
      id: `${current.runId}:step:${stepId}:${event.seq}`,
      seq: event.seq,
      type: 'plan',
      label: event.status === 'completed' ? `完成任务 ${stepId}` : `开始任务 ${stepId}`,
      detail: event.searchQuery as string,
      status: event.status === 'completed' ? 'succeeded' : 'running',
      groupId,
      groupLabel,
    })
  }

  function recordRetrieval(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const round = typeof event.round === 'number' ? event.round : undefined
    const queries = event.queries as string[]
    const queryText = queries.length ? queries.join('；') : (event.query as string)
    const strategy = retrievalStrategyLabel(event.strategy as string | undefined)
    current.trace.push({
      id: `${current.runId}:retrieval:${event.seq}`,
      seq: event.seq,
      type: 'retrieval',
      label: round ? `第 ${round} 轮检索完成` : '检索完成',
      detail: `${strategy} · 查询：${queryText} · 召回 ${event.resultCount as number} 条，${event.relevantCount as number} 条可用`,
      status: 'succeeded',
      ...(round ? { round } : {}),
      ...activeTraceGroup(current),
    })
  }

  function recordRewrite(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const missing = event.missingAspects as string[]
    const detail = [
      `原查询：${event.previousQuery as string}`,
      `新查询：${event.rewrittenQuery as string}`,
      missing.length ? `待补充：${missing.join('、')}` : '',
    ].filter(Boolean).join(' · ')
    current.trace.push({
      id: `${current.runId}:rewrite:${event.seq}`,
      seq: event.seq,
      type: 'rewrite',
      label: '已优化检索问题',
      detail,
      status: 'succeeded',
      ...activeTraceGroup(current),
    })
  }

  function recordReplan(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const actionLabels: Record<string, string> = {
      continue: '继续执行当前计划',
      revise: '已调整任务计划',
      finish: '任务计划已完成',
    }
    current.trace.push({
      id: `${current.runId}:replan:${event.seq}`,
      seq: event.seq,
      type: 'plan',
      label: actionLabels[event.action as string] ?? '已更新任务计划',
      detail: event.reason as string,
      status: 'succeeded',
    })
  }

  function startTool(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const callId = event.toolCallId as string
    const id = `${current.runId}:tool:${callId}`
    const planGroup = activePlanGroup(current)
    const ownGroup = planGroup.groupId
      ? planGroup
      : { groupId: id, groupLabel: toolGroupLabel(event.toolName as string) }
    toolStartedAt.set(callId, performance.now())
    current.trace.push({
      id,
      seq: event.seq,
      type: 'tool',
      label: toolTraceLabel(event.toolName as string),
      detail: formatToolArguments(event.toolName as string, event.args as Record<string, unknown>),
      status: 'running',
      ...ownGroup,
    })
  }

  function finishTool(event: ChatSseEvent): void {
    const current = execution.value
    if (!current) return
    const callId = event.toolCallId as string
    const id = `${current.runId}:tool:${callId}`
    const trace = current.trace.find((item) => item.id === id)
    const startedAt = toolStartedAt.get(callId)
    const durationMs = startedAt === undefined ? undefined : Math.max(Math.round(performance.now() - startedAt), 0)
    toolStartedAt.delete(callId)
    const status = event.success ? 'succeeded' : 'failed'
    const result = `返回 ${event.resultCount as number} 项结果`
    if (trace) {
      trace.status = status
      trace.detail = [trace.detail, result].filter(Boolean).join(' · ')
      if (durationMs !== undefined) trace.durationMs = durationMs
      return
    }
    current.trace.push({
      id,
      seq: event.seq,
      type: 'tool',
      label: toolTraceLabel(event.toolName as string),
      detail: result,
      status,
      ...(durationMs !== undefined ? { durationMs } : {}),
      ...activeTraceGroup(current),
    })
  }

  function failRunningTrace(message: string): void {
    const current = execution.value
    if (!current) return
    for (const item of current.trace) {
      if (item.status !== 'running') continue
      item.status = 'failed'
      if (!item.detail) item.detail = message
    }
  }

  function updatePlanStep(event: ChatSseEvent): void {
    if (!execution.value) return
    const steps = execution.value.plan ?? []
    const stepId = event.stepId as number
    let step = steps.find((item) => item.stepId === stepId)
    if (!step) {
      step = {
        stepId,
        goal: event.goal as string,
        searchQuery: event.searchQuery as string,
        status: 'pending',
      }
      steps.push(step)
    }
    step.status = event.status === 'completed' ? 'completed' : 'running'
    execution.value.plan = steps
  }

  function applyReplan(event: ChatSseEvent): void {
    if (!execution.value || event.action !== 'revise') return
    const completed = (execution.value.plan ?? []).filter((step) => step.status === 'completed')
    execution.value.plan = [...completed, ...(event.remainingSteps as PlanStep[])]
  }

  function assistantMessage(turnId: string): ChatMessage | undefined {
    return messages.value.find((message) => message.id === `${turnId}:assistant`)
  }

  function updateConversationTitle(conversationId: string, firstQuestion: string): void {
    const conversation = conversations.value.find((item) => item.conversationId === conversationId)
    if (!conversation) return
    conversation.title = conversation.title === '新对话' ? shortTitle(firstQuestion) : conversation.title
    conversation.updatedAt = new Date().toISOString()
    conversations.value = [...conversations.value].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
    saveConversations()
  }

  function removeConversation(conversationId: string): void {
    conversations.value = conversations.value.filter((item) => item.conversationId !== conversationId)
    saveConversations()
    if (currentConversationId.value === conversationId) createConversation()
  }

  function saveConversations(): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations.value))
  }

  return {
    conversations,
    currentConversationId,
    messages,
    streaming,
    activeTurnId,
    activeRunId,
    currentStatus,
    execution,
    resumableTurnId,
    loadingHistory,
    error,
    thinkingEnabled,
    canSend,
    initialize,
    createConversation,
    selectConversation,
    refreshConversation,
    sendMessage,
    resumeTurn,
    stopChat,
    setThinkingEnabled,
    reconcileTurn,
  }
})

function readConversations(): Conversation[] {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    if (!Array.isArray(stored)) return []
    return stored.filter(isConversation).sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
  } catch {
    return []
  }
}

function readThinkingEnabled(): boolean {
  try {
    const stored = localStorage.getItem(THINKING_STORAGE_KEY)
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

function isConversation(value: unknown): value is Conversation {
  return Boolean(
    value &&
      typeof value === 'object' &&
      typeof (value as Conversation).conversationId === 'string' &&
      typeof (value as Conversation).title === 'string' &&
      typeof (value as Conversation).updatedAt === 'string',
  )
}

function placeholder(conversationId: string, turnId: string, status: ChatMessage['status']): ChatMessage {
  return {
    id: `${turnId}:assistant`,
    conversationId,
    turnId,
    runId: null,
    role: 'assistant',
    content: '',
    status,
    sources: [],
  }
}

function markNotRunSteps(execution: ExecutionInfo): void {
  for (const step of execution.plan ?? []) {
    if (step.status === 'pending' || step.status === 'running') step.status = 'not_run'
  }
}

function activeTraceGroup(execution: ExecutionInfo): Pick<ExecutionTraceItem, 'groupId' | 'groupLabel'> {
  const planGroup = activePlanGroup(execution)
  if (planGroup.groupId) return planGroup
  const activeTool = [...execution.trace]
    .reverse()
    .find((item) => item.type === 'tool' && item.status === 'running')
  return activeTool
    ? { groupId: activeTool.groupId ?? activeTool.id, groupLabel: activeTool.groupLabel ?? activeTool.label }
    : {}
}

function activePlanGroup(execution: ExecutionInfo): Pick<ExecutionTraceItem, 'groupId' | 'groupLabel'> {
  const step = execution.plan?.find((item) => item.status === 'running')
  return step
    ? { groupId: `plan:${step.stepId}`, groupLabel: `任务 ${step.stepId} · ${step.goal}` }
    : {}
}

function isEvaluationNode(node: string): boolean {
  return node === 'evidence_grader' || node === 'answer_evaluator'
}

function nodeTraceLabel(node: string): string {
  const labels: Record<string, string> = {
    initialize_turn: '准备本轮问答',
    router: '分析问题执行路径',
    general_chat: '生成通用回答',
    react_adapter: '执行 ReAct 工具流程',
    planner: '拆解复杂任务',
    executor: '选择下一个任务',
    retriever: '执行知识检索',
    retrieval_planner: '规划检索策略',
    retrieval_executor: '搜索知识库',
    evidence_grader: '评估检索证据',
    retrieval_refiner: '优化检索问题',
    context_builder: '整理有效证据',
    replanner: '调整任务计划',
    generator: '生成候选答案',
    answer_evaluator: '校验最终答案',
    reflection: '分析修正路径',
    finalize_answer: '提交最终答案',
  }
  return labels[node] ?? '执行 Agent 节点'
}

function nodeResultDetail(node: string, result?: Record<string, unknown>): string | undefined {
  if (!result) return undefined
  if (node === 'evidence_grader') {
    const sufficient = result.sufficient === true ? '证据充分' : '证据仍不足'
    const relevantCount = typeof result.relevant_count === 'number'
      ? `${result.relevant_count} 条有效证据`
      : ''
    const coverage = typeof result.coverage_score === 'number'
      ? `覆盖率 ${Math.round(result.coverage_score * 100)}%`
      : ''
    return [sufficient, relevantCount, coverage].filter(Boolean).join(' · ')
  }
  if (node === 'answer_evaluator') {
    const grounded = result.grounded === true ? '内容有证据支撑' : '证据支撑不足'
    const complete = result.complete === true ? '回答完整' : '回答仍不完整'
    return `${grounded} · ${complete}`
  }
  if (node === 'finalize_answer') {
    const answerStatus = result.answer_status === 'best_effort' ? '尽力回答' : '答案已接受'
    const sourceCount = typeof result.source_count === 'number' ? `引用 ${result.source_count} 个来源` : ''
    return [answerStatus, sourceCount].filter(Boolean).join(' · ')
  }
  return undefined
}

function routeTraceLabel(route: string): string {
  const labels: Record<string, string> = {
    general_chat: '已选择通用问答',
    react: '已选择 ReAct 工具执行',
    plan_execute: '已选择 Plan-Execute-Replan',
  }
  return labels[route] ?? '已确定执行路径'
}

function capabilityLabel(capability: string): string {
  const labels: Record<string, string> = {
    knowledge: '知识库',
    realtime_info: '实时信息',
    action: '外部操作',
  }
  return labels[capability] ?? ''
}

function retrievalStrategyLabel(strategy?: string): string {
  const labels: Record<string, string> = {
    single: '单查询',
    rewrite: '查询改写',
    multi_query: '多查询',
    decompose: '问题分解',
    next_hop: '多跳检索',
  }
  return strategy ? (labels[strategy] ?? '知识检索') : '知识检索'
}

function toolTraceLabel(toolName: string): string {
  const labels: Record<string, string> = {
    search_knowledge_base: '调用知识库检索',
    get_document_context: '读取文档上下文',
    get_document_info: '读取文档信息',
  }
  return labels[toolName] ?? '调用工具'
}

function toolGroupLabel(toolName: string): string {
  const labels: Record<string, string> = {
    search_knowledge_base: '知识库检索',
    get_document_context: '文档上下文',
    get_document_info: '文档信息',
  }
  return labels[toolName] ?? '工具执行'
}

function formatToolArguments(toolName: string, args: Record<string, unknown>): string | undefined {
  if (toolName === 'search_knowledge_base') {
    const query = typeof args.query === 'string' ? `查询：${shortTraceText(args.query)}` : ''
    const topK = typeof args.top_k === 'number' ? `Top ${args.top_k}` : ''
    return [query, topK].filter(Boolean).join(' · ') || undefined
  }
  if (toolName === 'get_document_context') {
    const chunkId = typeof args.chunk_id === 'string' ? `片段：${shortTraceText(args.chunk_id)}` : ''
    const window = typeof args.window === 'number' ? `上下文窗口：${args.window}` : ''
    return [chunkId, window].filter(Boolean).join(' · ') || undefined
  }
  if (toolName === 'get_document_info' && typeof args.document_id === 'string') {
    return `文档：${shortTraceText(args.document_id)}`
  }
  return undefined
}

function shortTraceText(value: string): string {
  return value.length > 120 ? `${value.slice(0, 120)}…` : value
}

function activityForNode(node: string): string {
  const labels: Record<string, string> = {
    router: '正在分析问题…',
    general_chat: '正在生成回答…',
    planner: '正在拆解任务…',
    retriever: '正在搜索知识库…',
    retrieval_planner: '正在规划检索策略…',
    retrieval_executor: '正在搜索知识库…',
    evidence_grader: '正在判断检索证据…',
    retrieval_refiner: '正在优化检索问题…',
    context_builder: '正在整理检索证据…',
    generator: '正在生成答案…',
    answer_evaluator: '正在校验答案…',
    reflection: '正在分析如何修正答案…',
    finalize_answer: '正在保存最终回答…',
  }
  return labels[node] ?? 'Agent 正在处理…'
}

function shortTitle(value: string): string {
  return value.length > 22 ? `${value.slice(0, 22)}…` : value
}

function toChatRequestError(error: unknown): ChatRequestError {
  return error instanceof ChatRequestError
    ? error
    : new ChatRequestError({ code: 'NETWORK_ERROR', message: '无法连接到服务，请确认后端已启动。' })
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}
