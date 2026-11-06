/** mock 数据库：localStorage 持久化，模拟后端 app.db（users/sessions/messages）。 */
import type { ChatMessage, Session } from '../types'
import { monthlyTrend } from './demoFlows'

const DB_KEY = 'nl2sql_mock_db_v1'

export interface MockUser {
  username: string
  password: string
}

export interface MockDB {
  users: MockUser[]
  sessions: Session[]
  messages: ChatMessage[]
}

const SEED_SESSION_ID = 'seed-session-001'

function seedDB(): MockDB {
  const now = new Date().toISOString()
  return {
    users: [{ username: 'admin', password: 'admin123' }],
    sessions: [
      { id: SEED_SESSION_ID, title: '示例：月度销售趋势', created_at: now, updated_at: now },
    ],
    messages: [
      {
        id: 'seed-msg-1',
        session_id: SEED_SESSION_ID,
        role: 'user',
        content: '2025 年各月销售额趋势',
        status: 'done',
        created_at: now,
      },
      {
        id: 'seed-msg-2',
        session_id: SEED_SESSION_ID,
        role: 'assistant',
        content: monthlyTrend.answer,
        sql: monthlyTrend.sql,
        chart_spec: monthlyTrend.chart,
        result: monthlyTrend.result,
        status: 'done',
        created_at: now,
      },
    ],
  }
}

export function loadDB(): MockDB {
  const raw = localStorage.getItem(DB_KEY)
  if (raw) {
    try {
      return JSON.parse(raw) as MockDB
    } catch {
      // 数据损坏时重建种子
    }
  }
  const db = seedDB()
  saveDB(db)
  return db
}

export function saveDB(db: MockDB): void {
  localStorage.setItem(DB_KEY, JSON.stringify(db))
}

/** 重置为种子数据（调试用）。 */
export function resetDB(): void {
  localStorage.removeItem(DB_KEY)
  loadDB()
}

export const delay = (ms = 200) => new Promise<void>((resolve) => setTimeout(resolve, ms))
