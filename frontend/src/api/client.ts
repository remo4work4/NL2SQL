/**
 * axios 实例：统一 baseURL 与鉴权头。
 * Phase 0 仅定义；Phase 2 接入真实后端，Phase 3 关闭 mock。
 */
import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'

/** localStorage 中 token 的键名（FR-15 登录认证） */
export const TOKEN_KEY = 'nl2sql_token'

export const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 401（token 过期/无效）：清除登录态回到登录页（FR-15 登录状态保持的兜底）
client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('nl2sql_username')
      if (!window.location.pathname.includes('login')) window.location.reload()
    }
    return Promise.reject(error)
  },
)
