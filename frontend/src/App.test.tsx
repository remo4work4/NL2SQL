import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import App from './App'
import { useAuthStore } from './store/authStore'

describe('App 入口（Phase 1）', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ token: null, username: null, loggingIn: false })
  })

  it('未登录时展示登录页', () => {
    render(<App />)
    expect(screen.getByText('智能数据分析系统')).toBeTruthy()
    expect(screen.getByPlaceholderText('用户名')).toBeTruthy()
    expect(screen.getByPlaceholderText('密码')).toBeTruthy()
  })
})
