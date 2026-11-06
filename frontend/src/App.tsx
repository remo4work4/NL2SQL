/** 应用入口：未登录 → 登录页；已登录 → 三栏主界面。 */
import { useEffect } from 'react'
import MainLayout from './components/MainLayout'
import LoginPage from './pages/LoginPage'
import { useAuthStore } from './store/authStore'
import { useSessionStore } from './store/sessionStore'

function App() {
  const token = useAuthStore((s) => s.token)
  const init = useSessionStore((s) => s.init)

  useEffect(() => {
    if (token) void init()
  }, [token, init])

  return token ? <MainLayout /> : <LoginPage />
}

export default App
