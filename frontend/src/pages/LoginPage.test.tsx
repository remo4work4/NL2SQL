import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAuthStore } from '../store/authStore'
import LoginPage from './LoginPage'

async function submit(username: string, password: string) {
  fireEvent.change(screen.getByPlaceholderText('用户名'), { target: { value: username } })
  fireEvent.change(screen.getByPlaceholderText('密码'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: '进入系统' }))
}

describe('LoginPage（FR-15，mock 校验）', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({ token: null, username: null, loggingIn: false })
  })

  it('正确账号密码登录成功并保持登录态', async () => {
    render(<LoginPage />)
    await submit('admin', 'admin123')
    await waitFor(() => expect(useAuthStore.getState().token).toBeTruthy())
    expect(useAuthStore.getState().username).toBe('admin')
    expect(localStorage.getItem('nl2sql_token')).toBeTruthy()
  })

  it('错误密码提示错误信息且不写入登录态', async () => {
    render(<LoginPage />)
    await submit('admin', 'wrong-password')
    await waitFor(() => expect(screen.getByText('用户名或密码错误')).toBeTruthy())
    expect(useAuthStore.getState().token).toBeNull()
  })
})
