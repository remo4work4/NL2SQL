/** 登录页（FR-15）：“观测台入口”——极光背景 + 玻璃卡片。 */
import { Button, Card, Flex, Form, Input, Typography } from 'antd'
import { LockOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { USE_MOCK } from '../api'
import { useAuthStore } from '../store/authStore'

interface LoginForm {
  username: string
  password: string
}

export default function LoginPage() {
  const login = useAuthStore((s) => s.login)
  const loggingIn = useAuthStore((s) => s.loggingIn)
  const [error, setError] = useState('')

  const onFinish = async (values: LoginForm) => {
    setError('')
    try {
      await login(values.username, values.password)
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请重试')
    }
  }

  return (
    <Flex align="center" justify="center" style={{ height: '100vh' }}>
      <div className="app-bg-grid" />
      <div
        className="aurora-blob"
        style={{ width: 480, height: 480, top: '-10%', left: '8%', background: 'rgba(77,163,255,0.22)' }}
      />
      <div
        className="aurora-blob b2"
        style={{ width: 560, height: 560, bottom: '-15%', right: '5%', background: 'rgba(124,108,240,0.20)' }}
      />
      <Card
        style={{
          width: 380,
          background: 'rgba(16,23,40,0.72)',
          backdropFilter: 'blur(18px)',
          WebkitBackdropFilter: 'blur(18px)',
          border: '1px solid rgba(148,163,184,0.16)',
          borderRadius: 16,
          boxShadow: '0 24px 64px rgba(3,6,16,0.55)',
          position: 'relative',
          zIndex: 1,
        }}
      >
        <Flex vertical align="center" style={{ marginBottom: 24 }}>
          <Flex
            align="center"
            justify="center"
            style={{
              width: 56,
              height: 56,
              borderRadius: 16,
              background: 'linear-gradient(135deg, #3d8bf5 0%, #7c6cf0 100%)',
              boxShadow: '0 0 32px rgba(77,163,255,0.35)',
            }}
          >
            <RobotOutlined style={{ fontSize: 28, color: '#fff' }} />
          </Flex>
          <div
            className="gradient-text"
            style={{ fontSize: 22, fontWeight: 600, letterSpacing: '0.08em', marginTop: 16 }}
          >
            智能数据分析系统
          </div>
          <Typography.Text type="secondary" style={{ marginTop: 6 }}>
            用自然语言提问，自动查询并可视化
          </Typography.Text>
        </Flex>
        <Form<LoginForm> onFinish={onFinish} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          {error && (
            <Typography.Text type="danger" style={{ display: 'block', marginBottom: 12 }}>
              {error}
            </Typography.Text>
          )}
          <Button className="btn-glow" type="primary" htmlType="submit" block loading={loggingIn}>
            进入系统
          </Button>
        </Form>
        {USE_MOCK && (
          <Typography.Text
            type="secondary"
            style={{ display: 'block', marginTop: 16, fontSize: 12, textAlign: 'center' }}
          >
            测试账号：admin / admin123
          </Typography.Text>
        )}
      </Card>
    </Flex>
  )
}
