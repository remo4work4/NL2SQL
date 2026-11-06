/** 左栏：会话管理（FR-8 新建/切换/删除，FR-12 重命名）+ 退出登录（FR-15）。 */
import { Button, Empty, Flex, Input, Modal, Popconfirm, Typography, theme } from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  LogoutOutlined,
  PlusOutlined,
  RobotOutlined,
} from '@ant-design/icons'
import { useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { useSessionStore } from '../store/sessionStore'
import type { Session } from '../api/types'

function formatTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function Sidebar() {
  const sessions = useSessionStore((s) => s.sessions)
  const currentId = useSessionStore((s) => s.currentId)
  const createSession = useSessionStore((s) => s.createSession)
  const selectSession = useSessionStore((s) => s.selectSession)
  const removeSession = useSessionStore((s) => s.removeSession)
  const renameSession = useSessionStore((s) => s.renameSession)
  const username = useAuthStore((s) => s.username)
  const logout = useAuthStore((s) => s.logout)
  const { token } = theme.useToken()

  const [renameTarget, setRenameTarget] = useState<Session | null>(null)
  const [renameValue, setRenameValue] = useState('')

  return (
    <Flex vertical style={{ height: '100%', padding: 12, gap: 8, minHeight: 0 }}>
      <Flex align="center" gap={10} style={{ padding: '4px 4px 12px', flexShrink: 0 }}>
        <Flex
          align="center"
          justify="center"
          style={{
            width: 30,
            height: 30,
            borderRadius: 9,
            background: 'linear-gradient(135deg, #3d8bf5 0%, #7c6cf0 100%)',
            flexShrink: 0,
          }}
        >
          <RobotOutlined style={{ fontSize: 16, color: '#fff' }} />
        </Flex>
        <Typography.Text strong style={{ fontSize: 15, letterSpacing: '0.04em' }}>
          智能数据分析
        </Typography.Text>
      </Flex>

      <Button
        type="primary"
        icon={<PlusOutlined />}
        block
        onClick={() => void createSession()}
        style={{ flexShrink: 0 }}
      >
        新建会话
      </Button>

      <Flex vertical flex={1} style={{ overflowY: 'auto', minHeight: 0, margin: '0 -4px' }}>
        {sessions.length === 0 ? (
          <Empty description="暂无会话" style={{ margin: 'auto' }} />
        ) : (
          sessions.map((item) => {
            const selected = item.id === currentId
            return (
              <div
                key={item.id}
                className="session-item"
                onClick={() => void selectSession(item.id)}
                style={{
                  background: selected ? 'rgba(77,163,255,0.12)' : undefined,
                  borderLeftColor: selected ? '#4da3ff' : undefined,
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Typography.Text
                    ellipsis
                    style={{
                      display: 'block',
                      fontSize: 13,
                      color: selected ? token.colorPrimary : undefined,
                    }}
                  >
                    {item.title}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                    {formatTime(item.updated_at)}
                  </Typography.Text>
                </div>
                <div className="session-actions">
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      setRenameTarget(item)
                      setRenameValue(item.title)
                    }}
                  />
                  <Popconfirm
                    title="删除该会话？"
                    description="会话中的消息将一并删除"
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => void removeSession(item.id)}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>
                </div>
              </div>
            )
          })
        )}
      </Flex>

      <Flex
        justify="space-between"
        align="center"
        style={{
          padding: '8px 4px 0',
          borderTop: `1px solid ${token.colorBorderSecondary}`,
          flexShrink: 0,
        }}
      >
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {username}
        </Typography.Text>
        <Button type="text" size="small" icon={<LogoutOutlined />} onClick={() => void logout()}>
          退出
        </Button>
      </Flex>

      <Modal
        open={!!renameTarget}
        title="重命名会话"
        okText="保存"
        cancelText="取消"
        onOk={() => {
          if (renameTarget && renameValue.trim()) {
            void renameSession(renameTarget.id, renameValue.trim())
          }
          setRenameTarget(null)
        }}
        onCancel={() => setRenameTarget(null)}
      >
        <Input
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onPressEnter={() => {
            if (renameTarget && renameValue.trim()) {
              void renameSession(renameTarget.id, renameValue.trim())
            }
            setRenameTarget(null)
          }}
          maxLength={30}
          placeholder="输入新的会话名称"
        />
      </Modal>
    </Flex>
  )
}
