/** 底部输入框（FR-1）：Enter 发送 / Shift+Enter 换行，流式期间禁用。 */
import { Button, Flex, Input, theme } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import { useState } from 'react'
import { useChatStore } from '../store/chatStore'

export default function ChatInput() {
  const [value, setValue] = useState('')
  const streaming = useChatStore((s) => s.streaming)
  const sendQuestion = useChatStore((s) => s.sendQuestion)
  const { token } = theme.useToken()

  const submit = () => {
    const q = value.trim()
    if (!q || streaming) return
    setValue('')
    void sendQuestion(q)
  }

  return (
    <Flex
      gap={8}
      align="flex-end"
      style={{ padding: '12px 16px', borderTop: `1px solid ${token.colorBorderSecondary}` }}
    >
      <Input.TextArea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="输入你的问题，如：2025 年各月销售额趋势（Enter 发送 / Shift+Enter 换行）"
        autoSize={{ minRows: 1, maxRows: 4 }}
      />
      <Button type="primary" icon={<SendOutlined />} onClick={submit} loading={streaming}>
        发送
      </Button>
    </Flex>
  )
}
