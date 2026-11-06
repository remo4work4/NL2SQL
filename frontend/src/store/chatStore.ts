/** 当前会话的消息流与流式状态（FR-1/2/4/5/6）。 */
import { create } from 'zustand'
import { chatStream } from '../api/chat'
import type { ChatMessage, ChatStreamEvent } from '../api/types'
import { useSessionStore } from './sessionStore'

export type ViewType = 'auto' | 'bar' | 'line' | 'pie' | 'table'

interface ChatState {
  messages: ChatMessage[]
  streaming: boolean
  /** 右栏图表视图类型：auto = 按 LLM 建议/前端推断 */
  viewType: ViewType
  load: (messages: ChatMessage[]) => void
  setViewType: (type: ViewType) => void
  sendQuestion: (question: string) => Promise<void>
  retry: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  streaming: false,
  viewType: 'auto',

  load: (messages) => set({ messages, viewType: 'auto' }),

  setViewType: (viewType) => set({ viewType }),

  sendQuestion: async (question) => {
    if (get().streaming || !question.trim()) return
    const sessionStore = useSessionStore.getState()
    const sessionId = await sessionStore.ensureSession()
    const isFirst = get().messages.length === 0
    const text = question.trim()
    const now = new Date().toISOString()

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      session_id: sessionId,
      role: 'user',
      content: text,
      status: 'done',
      created_at: now,
    }
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      session_id: sessionId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      created_at: now,
    }
    set((s) => ({ messages: [...s.messages, userMsg, assistantMsg], streaming: true, viewType: 'auto' }))

    // 首条消息后取前 20 字作为会话标题（FR-8）
    if (isFirst) {
      await sessionStore.renameSession(sessionId, text.slice(0, 20))
    }

    let errored = false
    const applyEvent = (event: ChatStreamEvent) => {
      if (event.event === 'error') errored = true
      set((s) => ({
        messages: s.messages.map((m) => {
          if (m.id !== assistantMsg.id) return m
          const next = { ...m }
          switch (event.event) {
            case 'answer':
              next.content = m.content + event.data.delta
              break
            case 'sql':
              next.sql = event.data.sql
              break
            case 'result':
              next.result = event.data
              break
            case 'chart':
              next.chart_spec = event.data
              break
            case 'error':
              next.error = event.data.message
              break
          }
          return next
        }),
      }))
    }

    try {
      await chatStream(sessionId, text, applyEvent)
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantMsg.id ? { ...m, status: errored ? 'error' : 'done' } : m,
        ),
        streaming: false,
      }))
    } catch (err) {
      const fallback = err instanceof Error ? err.message : '请求失败，请重试'
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantMsg.id ? { ...m, status: 'error', error: m.error ?? fallback } : m,
        ),
        streaming: false,
      }))
    }
    sessionStore.bumpSession(sessionId)
  },

  retry: () => {
    if (get().streaming) return
    const lastUser = [...get().messages].reverse().find((m) => m.role === 'user')
    if (lastUser) void get().sendQuestion(lastUser.content)
  },
}))
