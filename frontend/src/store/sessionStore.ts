/** 会话管理（FR-8/9/12）：列表、切换、新建、重命名、删除。 */
import { create } from 'zustand'
import * as api from '../api/sessions'
import type { Session } from '../api/types'
import { useChatStore } from './chatStore'

interface SessionState {
  sessions: Session[]
  currentId: string | null
  loading: boolean
  init: () => Promise<void>
  createSession: () => Promise<void>
  selectSession: (id: string) => Promise<void>
  renameSession: (id: string, title: string) => Promise<void>
  removeSession: (id: string) => Promise<void>
  ensureSession: () => Promise<string>
  /** 本地把会话移到列表顶部（updated_at 由 api 层维护） */
  bumpSession: (id: string) => void
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentId: null,
  loading: false,

  init: async () => {
    set({ loading: true })
    const sessions = await api.listSessions()
    set({ sessions, loading: false })
    const target = sessions[0]?.id ?? null
    if (target) await get().selectSession(target)
  },

  createSession: async () => {
    const session = await api.createSession()
    set((s) => ({ sessions: [session, ...s.sessions] }))
    await get().selectSession(session.id)
  },

  selectSession: async (id) => {
    const messages = await api.getSessionMessages(id)
    useChatStore.getState().load(messages)
    set({ currentId: id })
  },

  renameSession: async (id, title) => {
    await api.renameSession(id, title)
    set((s) => ({ sessions: s.sessions.map((x) => (x.id === id ? { ...x, title } : x)) }))
  },

  removeSession: async (id) => {
    await api.deleteSession(id)
    const sessions = get().sessions.filter((x) => x.id !== id)
    if (get().currentId === id) {
      const next = sessions[0]?.id ?? null
      if (next) {
        await get().selectSession(next)
      } else {
        useChatStore.getState().load([])
        set({ currentId: null })
      }
    }
    set({ sessions })
  },

  ensureSession: async () => {
    if (get().currentId) return get().currentId as string
    await get().createSession()
    return get().currentId as string
  },

  bumpSession: (id) => {
    set((s) => {
      const target = s.sessions.find((x) => x.id === id)
      if (!target) return s
      const others = s.sessions.filter((x) => x.id !== id)
      return { sessions: [{ ...target, updated_at: new Date().toISOString() }, ...others] }
    })
  },
}))
