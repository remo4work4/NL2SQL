/** 中栏消息流：自动滚底、空状态引导、示例问题快捷入口。 */
import { Button, Empty, Flex, Space, Typography } from 'antd'
import { useEffect, useRef } from 'react'
import { useChatStore } from '../store/chatStore'
import MessageBubble from './MessageBubble'

const SUGGESTIONS = ['2025 年各月销售额趋势', '各品类销售额占比', '各地区销售额对比']

interface MessageListProps {
  onAsk: (question: string) => void
}

export default function MessageList({ onAsk }: MessageListProps) {
  const messages = useChatStore((s) => s.messages)
  const retry = useChatStore((s) => s.retry)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <Flex vertical align="center" justify="center" gap={12} style={{ flex: 1, padding: 24 }}>
        <Empty description="用自然语言提问，我会查询数据并生成图表" />
        <Space wrap style={{ justifyContent: 'center' }}>
          {SUGGESTIONS.map((q) => (
            <Button key={q} size="small" onClick={() => onAsk(q)}>
              {q}
            </Button>
          ))}
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          试试追问："那按品类再看一下" 或输入含"删除"的问题体验安全拦截
        </Typography.Text>
      </Flex>
    )
  }

  return (
    <Flex vertical gap={16} style={{ padding: 16, overflowY: 'auto', flex: 1, minHeight: 0 }}>
      {messages.map((m, i) => (
        <MessageBubble
          key={m.id}
          message={m}
          onRetry={i === messages.length - 1 ? () => retry() : undefined}
        />
      ))}
      <div ref={bottomRef} />
    </Flex>
  )
}
