import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp, ConfigProvider, theme } from 'antd'
import type { ThemeConfig } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App.tsx'
import './index.css'

/** 深色"数据观测台"主题：深蓝夜空 + 蓝紫极光；界面安静，颜色留给图表。 */
const appTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#4da3ff',
    colorInfo: '#4da3ff',
    colorLink: '#4da3ff',
    colorBgBase: '#0d1322',
    colorBgContainer: '#101728',
    colorBgElevated: '#141c31',
    colorBorder: 'rgba(148,163,184,0.16)',
    colorBorderSecondary: 'rgba(148,163,184,0.10)',
    colorText: '#e8ecf6',
    colorTextSecondary: '#9aa4b8',
    colorTextTertiary: '#5f6b84',
    borderRadius: 10,
    fontFamily:
      "-apple-system, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Segmented: {
      itemSelectedBg: 'rgba(77,163,255,0.16)',
      itemSelectedColor: '#8ec5ff',
    },
    Table: {
      headerBg: 'rgba(148,163,184,0.07)',
      headerColor: '#9aa4b8',
      borderColor: 'rgba(148,163,184,0.10)',
    },
    Modal: {
      contentBg: '#131a2e',
      headerBg: '#131a2e',
    },
  },
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={appTheme}>
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
)
