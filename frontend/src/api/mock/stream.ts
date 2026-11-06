/** 模拟 SSE 事件流：按协议顺序 answer* → sql → result → chart → done（或 error）。 */
import type { ChatStreamEvent } from '../types'
import { routeDemoFlow } from './demoFlows'

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

/** 把回答文本切成约 8 字一块，模拟打字机流式输出 */
function chunkText(text: string, size = 8): string[] {
  const out: string[] = []
  for (let i = 0; i < text.length; i += size) out.push(text.slice(i, i + size))
  return out
}

export async function* mockChatStream(question: string): AsyncGenerator<ChatStreamEvent> {
  const flow = routeDemoFlow(question)
  if ('error' in flow) {
    await sleep(600)
    yield { event: 'error', data: flow.error }
    return
  }
  for (const delta of chunkText(flow.answer)) {
    await sleep(45)
    yield { event: 'answer', data: { delta } }
  }
  await sleep(250)
  yield { event: 'sql', data: { sql: flow.sql } }
  await sleep(300)
  yield { event: 'result', data: flow.result }
  await sleep(200)
  yield { event: 'chart', data: flow.chart }
  await sleep(150)
  yield { event: 'done', data: { message_id: crypto.randomUUID() } }
}
