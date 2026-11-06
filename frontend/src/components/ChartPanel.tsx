/** 右栏：可视化图表区（FR-7 自动推断实时渲染 / FR-11 类型切换 / 表格视图 / 数据概览指标条）。 */
import { Empty, Flex, Segmented, Skeleton, Table, Typography, theme } from 'antd'
import { useMemo } from 'react'
import { useChatStore } from '../store/chatStore'
import type { ViewType } from '../store/chatStore'
import { inferChartSpec } from '../utils/chartInfer'
import {
  buildChartOption,
  buildTableColumns,
  computeStats,
  rowsToDataSource,
} from '../utils/chartOption'
import EChart from './EChart'

const VIEW_OPTIONS: { label: string; value: ViewType }[] = [
  { label: '自动', value: 'auto' },
  { label: '柱状图', value: 'bar' },
  { label: '折线图', value: 'line' },
  { label: '饼图', value: 'pie' },
  { label: '表格', value: 'table' },
]

export default function ChartPanel() {
  const messages = useChatStore((s) => s.messages)
  const streaming = useChatStore((s) => s.streaming)
  const viewType = useChatStore((s) => s.viewType)
  const setViewType = useChatStore((s) => s.setViewType)
  const { token } = theme.useToken()

  // 最近一条带结果（或正在生成）的助手消息
  const latest = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((m) => m.role === 'assistant' && (m.result || m.status !== 'done')),
    [messages],
  )

  // 图表规格：LLM 建议优先，前端规则兜底（FR-7）
  const effectiveSpec = useMemo(() => {
    if (!latest?.result) return null
    return latest.chart_spec ?? inferChartSpec(latest.result)
  }, [latest])

  const renderType: 'bar' | 'line' | 'pie' =
    viewType === 'auto'
      ? (effectiveSpec?.chart_type ?? 'bar')
      : viewType === 'table'
        ? 'bar'
        : viewType

  const option =
    effectiveSpec && latest?.result
      ? buildChartOption(effectiveSpec, latest.result, renderType)
      : null

  // 数据概览指标条（图表视图才展示，表格视图不需要）
  const stats = useMemo(() => {
    if (!latest?.result || !effectiveSpec || viewType === 'table') return []
    return computeStats(latest.result, effectiveSpec.y ?? [])
  }, [latest, effectiveSpec, viewType])

  let body: React.ReactNode
  if (streaming && latest && !latest.result && !latest.error) {
    body = <Skeleton active paragraph={{ rows: 6 }} style={{ padding: 24, flex: 1 }} />
  } else if (latest?.status === 'error') {
    body = <Empty description="查询失败，图表不可用" style={{ margin: 'auto' }} />
  } else if (latest && latest.status === 'done' && !latest.result) {
    body = <Empty description="本次回答没有图表数据" style={{ margin: 'auto' }} />
  } else if (latest?.result && latest.result.row_count === 0) {
    body = <Empty description="查询无数据" style={{ margin: 'auto' }} />
  } else if (latest?.result && viewType === 'table') {
    body = (
      <Flex flex={1} vertical style={{ minHeight: 0, padding: 12 }}>
        <Flex flex={1} style={{ overflow: 'auto', minHeight: 0 }}>
          <Table
            size="small"
            columns={buildTableColumns(latest.result.columns)}
            dataSource={rowsToDataSource(latest.result)}
            rowKey="_key"
            pagination={false}
            scroll={{ x: 'max-content' }}
          />
        </Flex>
        {latest.result.truncated && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            结果已截断，仅显示前 {latest.result.rows.length} 行
          </Typography.Text>
        )}
      </Flex>
    )
  } else if (option && latest?.result) {
    body = (
      <Flex flex={1} style={{ minHeight: 0, padding: '4px 14px 14px' }}>
        <EChart option={option} />
      </Flex>
    )
  } else {
    body = (
      <Empty
        description={
          <Typography.Text type="secondary">提问后，这里会实时展示可视化图表</Typography.Text>
        }
        style={{ margin: 'auto' }}
      />
    )
  }

  const title = effectiveSpec?.title ?? latest?.chart_spec?.title ?? '可视化结果'

  return (
    <Flex vertical style={{ height: '100%' }}>
      <Flex
        vertical
        gap={10}
        style={{ padding: '14px 16px 10px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}
      >
        <Flex align="center" gap={8}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 3,
              background: 'linear-gradient(135deg, #4da3ff 0%, #7c6cf0 100%)',
              flexShrink: 0,
            }}
          />
          <Typography.Text strong ellipsis style={{ fontSize: 15 }}>
            {title}
          </Typography.Text>
        </Flex>
        <Segmented
          size="small"
          value={viewType}
          onChange={(v) => setViewType(v as ViewType)}
          options={VIEW_OPTIONS}
        />
      </Flex>

      {stats.length > 0 && (
        <Flex gap={8} style={{ padding: '12px 16px 0' }}>
          {stats.map((s) => (
            <Flex
              key={s.label}
              vertical
              flex={1}
              style={{
                background: 'rgba(148,163,184,0.06)',
                border: '1px solid rgba(148,163,184,0.10)',
                borderRadius: 10,
                padding: '8px 12px',
              }}
            >
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                {s.label}
              </Typography.Text>
              <Typography.Text
                strong
                style={{ fontSize: 17, fontVariantNumeric: 'tabular-nums', letterSpacing: '0.01em' }}
              >
                {s.value}
              </Typography.Text>
            </Flex>
          ))}
        </Flex>
      )}

      <Flex flex={1} vertical style={{ minHeight: 0 }}>
        {body}
      </Flex>
    </Flex>
  )
}
