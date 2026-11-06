/** 中栏：问答区（FR-1/2/4/5/6）。 */
import { Flex, Typography, theme } from 'antd'
import { useChatStore } from '../store/chatStore'
import { useSessionStore } from '../store/sessionStore'
import ChatInput from './ChatInput'
import MessageList from './MessageList'

export default function ChatPanel() {
  const currentId = useSessionStore((s) => s.currentId)
  const sessions = useSessionStore((s) => s.sessions)
  const sendQuestion = useChatStore((s) => s.sendQuestion)
  const { token } = theme.useToken()

  const title = sessions.find((s) => s.id === currentId)?.title ?? '新会话'

  return (
    <Flex vertical style={{ height: '100%', minWidth: 0 }}>
      <Flex
        align="center"
        style={{
          padding: '10px 16px',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
          flexShrink: 0,
        }}
      >
        <Typography.Text strong ellipsis style={{ fontSize: 15 }}>
          {title}
        </Typography.Text>
      </Flex>
      <MessageList onAsk={(q) => void sendQuestion(q)} />
      <ChatInput />
    </Flex>
  )
}
