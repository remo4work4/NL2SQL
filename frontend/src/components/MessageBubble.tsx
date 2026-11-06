/** 单条消息气泡：用户/助手，含流式打字机、SQL 块、结果表、错误重试。 */
import { Alert, Avatar, Button, Flex, Spin, Typography, theme } from 'antd'
import { RobotOutlined, UserOutlined } from '@ant-design/icons'
import type { ChatMessage } from '../api/types'
import ResultTable from './ResultTable'
import SqlBlock from './SqlBlock'

interface MessageBubbleProps {
  message: ChatMessage
  onRetry?: () => void
}

export default function MessageBubble({ message, onRetry }: MessageBubbleProps) {
  const { token } = theme.useToken()

  if (message.role === 'user') {
    return (
      <Flex justify="flex-end" gap={8} align="flex-start">
        <div
          style={{
            maxWidth: '75%',
            background: 'linear-gradient(135deg, #3d8bf5 0%, #4da3ff 100%)',
            color: '#fff',
            padding: '8px 14px',
            borderRadius: 12,
            borderBottomRightRadius: 4,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            fontSize: 14,
            boxShadow: '0 4px 16px rgba(77,163,255,0.25)',
          }}
        >
          {message.content}
        </div>
        <Avatar size={32} icon={<UserOutlined />} style={{ flexShrink: 0 }} />
      </Flex>
    )
  }

  return (
    <Flex gap={8} align="flex-start">
      <Avatar
        size={32}
        icon={<RobotOutlined />}
        style={{ background: token.colorPrimary, flexShrink: 0 }}
      />
      <Flex vertical gap={4} style={{ maxWidth: '85%', minWidth: 0, flex: 1 }}>
        <div
          style={{
            background: token.colorFillQuaternary,
            padding: '10px 14px',
            borderRadius: 12,
            borderTopLeftRadius: 4,
            wordBreak: 'break-word',
            minWidth: 0,
          }}
        >
          {message.status === 'streaming' && !message.content ? (
            <Flex gap={8} align="center">
              <Spin size="small" />
              <Typography.Text type="secondary">正在分析…</Typography.Text>
            </Flex>
          ) : (
            <Typography.Text style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>
              {message.content}
              {message.status === 'streaming' && '▍'}
            </Typography.Text>
          )}
          {message.sql && <SqlBlock sql={message.sql} />}
          {message.result && <ResultTable result={message.result} />}
        </div>
        {message.status === 'error' && (
          <Alert
            type="error"
            showIcon
            message={message.error ?? '请求失败，请重试'}
            action={
              onRetry ? (
                <Button size="small" onClick={onRetry}>
                  重试
                </Button>
              ) : undefined
            }
          />
        )}
      </Flex>
    </Flex>
  )
}
