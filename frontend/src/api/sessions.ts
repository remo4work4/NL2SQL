/** 会话管理接口（FR-8/9/12）：mock 模式操作本地 mock 数据库。 */
import { client } from './client'
import { USE_MOCK } from './index'
import { delay, loadDB, saveDB } from './mock/db'
import type { ChatMessage, Session } from './types'

export async function listSessions(): Promise<Session[]> {
  if (USE_MOCK) {
    await delay(200)
    return [...loadDB().sessions].sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  }
  const { data } = await client.get<Session[]>('/api/sessions')
  return data
}

export async function createSession(title = '新会话'): Promise<Session> {
  if (USE_MOCK) {
    await delay(150)
    const db = loadDB()
    const now = new Date().toISOString()
    const session: Session = { id: crypto.randomUUID(), title, created_at: now, updated_at: now }
    db.sessions.push(session)
    saveDB(db)
    return session
  }
  const { data } = await client.post<Session>('/api/sessions', { title })
  return data
}

export async function renameSession(id: string, title: string): Promise<void> {
  if (USE_MOCK) {
    await delay(100)
    const db = loadDB()
    const session = db.sessions.find((s) => s.id === id)
    if (session) {
      session.title = title
      session.updated_at = new Date().toISOString()
      saveDB(db)
    }
    return
  }
  await client.patch(`/api/sessions/${id}`, { title })
}

export async function deleteSession(id: string): Promise<void> {
  if (USE_MOCK) {
    await delay(100)
    const db = loadDB()
    db.sessions = db.sessions.filter((s) => s.id !== id)
    db.messages = db.messages.filter((m) => m.session_id !== id)
    saveDB(db)
    return
  }
  await client.delete(`/api/sessions/${id}`)
}

export async function getSessionMessages(sessionId: string): Promise<ChatMessage[]> {
  if (USE_MOCK) {
    await delay(200)
    return loadDB()
      .messages.filter((m) => m.session_id === sessionId)
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
  }
  const { data } = await client.get<{ messages: ChatMessage[] }>(`/api/sessions/${sessionId}`)
  return data.messages
}

/** mock：持久化一条消息；真实模式下消息由后端在流结束时保存，前端无需调用。 */
export async function addMessage(message: ChatMessage): Promise<void> {
  if (!USE_MOCK) return
  const db = loadDB()
  db.messages.push(message)
  saveDB(db)
}

/** mock：把会话更新时间拨到现在（真实模式下由后端维护）。 */
export async function touchSession(id: string): Promise<void> {
  if (!USE_MOCK) return
  const db = loadDB()
  const session = db.sessions.find((s) => s.id === id)
  if (session) {
    session.updated_at = new Date().toISOString()
    saveDB(db)
  }
}
