/** 登录态（FR-15）：token 持久化到 localStorage，刷新页面保持登录状态。 */
import { create } from 'zustand'
import { login as apiLogin, logout as apiLogout } from '../api/auth'
import { TOKEN_KEY } from '../api/client'

const USERNAME_KEY = 'nl2sql_username'

interface AuthState {
  token: string | null
  username: string | null
  loggingIn: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

function restore() {
  return {
    token: localStorage.getItem(TOKEN_KEY),
    username: localStorage.getItem(USERNAME_KEY),
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  ...restore(),
  loggingIn: false,

  login: async (username, password) => {
    set({ loggingIn: true })
    try {
      const { token } = await apiLogin(username, password)
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USERNAME_KEY, username)
      set({ token, username, loggingIn: false })
    } catch (err) {
      set({ loggingIn: false })
      throw err
    }
  },

  logout: async () => {
    await apiLogout().catch(() => {})
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USERNAME_KEY)
    set({ token: null, username: null })
  },
}))
