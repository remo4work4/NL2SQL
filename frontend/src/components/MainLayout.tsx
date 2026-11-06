/** 三栏主界面：左 会话管理 / 中 问答区 / 右 可视化图表区（玻璃面板材质）。 */
import { Layout } from 'antd'
import type { CSSProperties } from 'react'
import ChartPanel from './ChartPanel'
import ChatPanel from './ChatPanel'
import Sidebar from './Sidebar'

const GLASS: CSSProperties = {
  background: 'rgba(13,19,34,0.78)',
  backdropFilter: 'blur(18px)',
  WebkitBackdropFilter: 'blur(18px)',
}

const HAIRLINE = '1px solid rgba(148,163,184,0.12)'

export default function MainLayout() {
  return (
    <div style={{ height: '100vh' }}>
      <div className="app-bg-grid" />
      <Layout style={{ height: '100%', background: 'transparent' }}>
        <Layout.Sider width={260} style={{ ...GLASS, overflow: 'hidden' }}>
          <Sidebar />
        </Layout.Sider>
        <Layout.Content
          style={{
            ...GLASS,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            borderLeft: HAIRLINE,
            borderRight: HAIRLINE,
          }}
        >
          <ChatPanel />
        </Layout.Content>
        <Layout.Sider width="42%" style={{ ...GLASS, overflow: 'hidden' }}>
          <ChartPanel />
        </Layout.Sider>
      </Layout>
    </div>
  )
}
