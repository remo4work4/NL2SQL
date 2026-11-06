/** 对话流式接口：mock 模式模拟 SSE 事件序列；真实模式用 fetch 流解析后端 SSE（Phase 3 启用）。 */
import { API_BASE_URL, TOKEN_KEY } from './client'
import { USE_MOCK } from './index'
import { mockChatStream } from './mock/stream'
import { addMessage, touchSession } from './sessions'
import type { ChatMessage, ChatStreamEvent } from './types'

export type ChatEventCallback = (event: ChatStreamEvent) => void

/** 按事件协议更新消息对象（mock 持久化用） */
function applyEvent(msg: ChatMessage, event: ChatStreamEvent): void {
  switch (event.event) {
    case 'answer':
      msg.content += event.data.delta
      break
    case 'sql':
      msg.sql = event.data.sql
      break
    case 'result':
      msg.result = event.data
      break
    case 'chart':
      msg.chart_spec = event.data
      break
    case 'error':
      msg.error = event.data.message
      break
    case 'done':
      break
  }
}

/** 解析一个 SSE 事件块（event:/data: 格式，兼容 \r\n 行分隔） */
function parseSSE(chunk: string): ChatStreamEvent | null {
  const lines = chunk.replace(/\r/g, '').split('\n')
  const eventLine = lines.find((l) => l.startsWith('event:'))
  const dataLines = lines.filter((l) => l.startsWith('data:'))
  if (!eventLine || dataLines.length === 0) return null
  try {
    return {
      event: eventLine.slice('event:'.length).trim(),
      data: JSON.parse(dataLines.map((l) => l.slice('data:'.length).trimStart()).join('\n')),
    } as ChatStreamEvent
  } catch {
    return null
  }
}

/**
 * 发起一轮对话并流式回调事件。
 * mock 模式下同时把用户消息与助手消息持久化到本地 mock 数据库（FR-9 历史回看）。
 */
export async function chatStream(
  sessionId: string,
  question: string,
  onEvent: ChatEventCallback,
): Promise<void> {
  const now = new Date().toISOString()
  const userMsg: ChatMessage = {
    id: crypto.randomUUID(),
    session_id: sessionId,
    role: 'user',
    content: question,
    status: 'done',
    created_at: now,
  }

  if (USE_MOCK) {
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      session_id: sessionId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      created_at: now,
    }
    await addMessage(userMsg)
    for await (const event of mockChatStream(question)) {
      onEvent(event)
      applyEvent(assistantMsg, event)
    }
    assistantMsg.status = assistantMsg.error ? 'error' : 'done'
    await addMessage(assistantMsg)
    await touchSession(sessionId)
    return
  }

  // ---- 真实后端（Phase 3 联调启用）----
  const token = localStorage.getItem(TOKEN_KEY)
  const resp = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message: question }),
  })
  if (!resp.ok || !resp.body) throw new Error(`请求失败（HTTP ${resp.status}）`)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminated = false // 收到 done/error 事件才算正常终止
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE 块分隔为 \r\n\r\n 或 \n\n，两种都要兼容
    const parts = buffer.split(/\r\n\r\n|\n\n/)
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const event = parseSSE(part)
      if (event) {
        onEvent(event)
        if (event.event === 'done' || event.event === 'error') terminated = true
      }
    }
  }
  if (!terminated) throw new Error('连接中断，请重试')
}
