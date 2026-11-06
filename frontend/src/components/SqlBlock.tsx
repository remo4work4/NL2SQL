/** SQL 代码块展示 + 一键复制（FR-2）。 */
import { App, Button, theme } from 'antd'
import { CopyOutlined } from '@ant-design/icons'

export default function SqlBlock({ sql }: { sql: string }) {
  const { message } = App.useApp()
  const { token } = theme.useToken()

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql)
      message.success('SQL 已复制')
    } catch {
      message.error('复制失败')
    }
  }

  return (
    <div
      style={{
        position: 'relative',
        marginTop: 8,
        borderRadius: 8,
        overflow: 'hidden',
        border: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      <pre
        style={{
          margin: 0,
          padding: '10px 12px',
          background: '#0d1117',
          color: '#e6edf3',
          fontSize: 12.5,
          lineHeight: 1.6,
          overflowX: 'auto',
          fontFamily: "Consolas, 'Courier New', monospace",
        }}
      >
        {sql}
      </pre>
      <Button
        size="small"
        type="text"
        icon={<CopyOutlined />}
        onClick={() => void copy()}
        style={{ position: 'absolute', top: 4, right: 4, color: '#8b949e' }}
      />
    </div>
  )
}
