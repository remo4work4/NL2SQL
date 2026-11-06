/** 登录认证接口（FR-15）：mock 模式校验本地用户表，真实模式调用后端。 */
import { client } from './client'
import { USE_MOCK } from './index'
import { delay, loadDB } from './mock/db'
import type { LoginResponse } from './types'

export async function login(username: string, password: string): Promise<LoginResponse> {
  if (USE_MOCK) {
    await delay(400)
    const user = loadDB().users.find((u) => u.username === username && u.password === password)
    if (!user) throw new Error('用户名或密码错误')
    return { token: `mock-token-${crypto.randomUUID()}`, username: user.username }
  }
  const { data } = await client.post<LoginResponse>('/api/auth/login', { username, password })
  return data
}

export async function logout(): Promise<void> {
  if (USE_MOCK) {
    await delay(100)
    return
  }
  await client.post('/api/auth/logout')
}
