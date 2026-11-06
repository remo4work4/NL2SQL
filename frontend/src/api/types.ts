/** 与后端接口协议对齐的类型定义（需求文档第 7 章）。 */

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface QueryResult {
  columns: string[]
  rows: (string | number)[][]
  row_count: number
  truncated: boolean
}

export interface ChartSpec {
  chart_type: 'bar' | 'line' | 'pie'
  title?: string
  x?: string
  y?: string[]
}

export interface ChatMessage {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  sql?: string | null
  chart_spec?: ChartSpec | null
  result?: QueryResult | null
  status: 'streaming' | 'done' | 'error'
  error?: string | null
  created_at: string
}

export interface LoginResponse {
  token: string
  username: string
}

/** SSE 事件协议（需求文档 7.2 节） */
export type ChatStreamEvent =
  | { event: 'answer'; data: { delta: string } }
  | { event: 'sql'; data: { sql: string } }
  | { event: 'result'; data: QueryResult }
  | { event: 'chart'; data: ChartSpec }
  | { event: 'done'; data: { message_id: string } }
  | { event: 'error'; data: { code: string; message: string } }
