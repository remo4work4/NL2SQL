/** 由图表规格 + 查询结果构建 ECharts option（柔和高级风：渐变填充、圆角、软阴影 tooltip）。 */
import * as echarts from 'echarts/core'
import type { EChartsOption } from 'echarts'
import type { ChartSpec, QueryResult } from '../api/types'
import { CATEGORICAL, CHROME, FONT_FAMILY } from './palette'

export function fmtNumber(v: number): string {
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function rgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/** 向白色方向提亮（柔和渐变用） */
function lighten(hex: string, t: number): string {
  const c = (s: number) => {
    const v = parseInt(hex.slice(s, s + 2), 16)
    return Math.round(v + (255 - v) * t)
  }
  return `rgb(${c(1)}, ${c(3)}, ${c(5)})`
}

/** 结果行 → antd Table dataSource */
export function rowsToDataSource(result: QueryResult): Record<string, unknown>[] {
  const { columns, rows } = result
  return rows.map((r, i) => {
    const row: Record<string, unknown> = { _key: i }
    columns.forEach((c, j) => {
      row[c] = r[j]
    })
    return row
  })
}

export function buildTableColumns(columns: string[]) {
  return columns.map((c) => ({
    title: c,
    dataIndex: c,
    key: c,
    render: (v: unknown) => (typeof v === 'number' ? fmtNumber(v) : String(v)),
  }))
}

/** 从结果中提取 x 轴取值与 y 数值列 */
function extract(result: QueryResult, spec: ChartSpec) {
  const xCol = spec.x && result.columns.includes(spec.x) ? spec.x : result.columns[0]
  const xIdx = result.columns.indexOf(xCol)
  const numericCols = result.columns.filter(
    (_col, i) => i !== xIdx && result.rows.some((r) => typeof r[i] === 'number'),
  )
  const yCols = (spec.y ?? [])
    .filter((c) => result.columns.includes(c) && c !== xCol)
    .concat(numericCols)
    .filter((c, i, arr) => arr.indexOf(c) === i)
    .slice(0, 2)
  return {
    xIdx,
    xValues: result.rows.map((r) => String(r[xIdx])),
    yCols,
  }
}

function baseTooltip(type: 'bar' | 'line' | 'pie') {
  return {
    trigger: type === 'pie' ? ('item' as const) : ('axis' as const),
    ...(type !== 'pie'
      ? { axisPointer: { type: 'line' as const, lineStyle: { color: 'rgba(240,239,236,0.4)' } } }
      : {}),
    // 暗色表面上的反白浮层 + 圆角软阴影
    backgroundColor: '#f0efec',
    borderWidth: 0,
    borderRadius: 8,
    padding: [10, 14] as [number, number],
    extraCssText: 'box-shadow: 0 10px 32px rgba(3,6,16,0.4);',
    textStyle: { color: '#0b0b0b', fontFamily: FONT_FAMILY, fontSize: 12 },
    valueFormatter: (v: unknown) => (typeof v === 'number' ? fmtNumber(v) : String(v)),
  }
}

/** 数据概览统计（图表区指标条）：总和 / 均值 / 峰值 */
export function computeStats(
  result: QueryResult,
  yCols: string[],
): { label: string; value: string }[] {
  const { columns, rows } = result
  const yCol =
    yCols.find((c) => columns.includes(c)) ??
    columns.find((_col, i) => rows.some((r) => typeof r[i] === 'number'))
  if (!yCol) return []
  const yIdx = columns.indexOf(yCol)
  const values = rows
    .map((r) => r[yIdx])
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (values.length === 0) return []
  const sum = values.reduce((a, b) => a + b, 0)
  return [
    { label: '总和', value: fmtNumber(sum) },
    { label: '均值', value: fmtNumber(sum / values.length) },
    { label: '峰值', value: fmtNumber(Math.max(...values)) },
  ]
}

export function buildChartOption(
  spec: ChartSpec,
  result: QueryResult,
  type: 'bar' | 'line' | 'pie',
): EChartsOption {
  const { xIdx, xValues, yCols } = extract(result, spec)

  if (type === 'pie') {
    const yIdx = result.columns.indexOf(yCols[0] ?? result.columns[1])
    const data = result.rows.map((r, i) => ({
      name: String(r[xIdx]),
      value: Number(r[yIdx]),
      itemStyle: { color: CATEGORICAL[i % CATEGORICAL.length] },
    }))
    return {
      backgroundColor: 'transparent',
      color: CATEGORICAL,
      tooltip: baseTooltip('pie'),
      series: [
        {
          type: 'pie',
          radius: ['38%', '70%'],
          center: ['50%', '46%'],
          data,
          itemStyle: { borderRadius: 4, borderColor: '#0d1322', borderWidth: 2 },
          label: {
            color: CHROME.inkSecondary,
            fontFamily: FONT_FAMILY,
            fontSize: 12,
            formatter: '{b} {d}%',
          },
          labelLine: { lineStyle: { color: '#4a4a46' } },
          emphasis: { itemStyle: { shadowBlur: 14, shadowColor: 'rgba(3,6,16,0.45)' } },
        },
      ],
    }
  }

  const series = yCols.map((col, i) => {
    const yIdx = result.columns.indexOf(col)
    const data = result.rows.map((r) => Number(r[yIdx]))
    const color = CATEGORICAL[i % CATEGORICAL.length]
    if (type === 'line') {
      return {
        name: col,
        type: 'line' as const,
        data,
        smooth: 0.35,
        showSymbol: false,
        symbol: 'circle',
        symbolSize: 7,
        lineStyle: { width: 2, color },
        itemStyle: { color, borderColor: 'rgba(255,255,255,0.7)', borderWidth: 1 },
        areaStyle: {
          // 柔和渐变面积填充
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: rgba(color, 0.26) },
            { offset: 1, color: rgba(color, 0.02) },
          ]),
        },
        emphasis: { focus: 'series' as const },
      }
    }
    return {
      name: col,
      type: 'bar' as const,
      data,
      barMaxWidth: 32,
      barCategoryGap: '38%',
      itemStyle: {
        // 顶部提亮的柔和渐变柱体
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: lighten(color, 0.22) },
          { offset: 1, color },
        ]),
        borderRadius: [6, 6, 0, 0],
      },
      emphasis: { focus: 'series' as const },
    }
  })

  return {
    backgroundColor: 'transparent',
    color: CATEGORICAL,
    tooltip: baseTooltip(type),
    legend:
      yCols.length >= 2
        ? {
            top: 0,
            icon: 'circle',
            itemWidth: 8,
            itemHeight: 8,
            textStyle: { color: CHROME.inkSecondary, fontFamily: FONT_FAMILY },
          }
        : undefined,
    grid: {
      left: 48,
      right: 20,
      top: yCols.length >= 2 ? 36 : 20,
      bottom: 32,
    },
    xAxis: {
      type: 'category',
      data: xValues,
      boundaryGap: type === 'bar', // 折线图贴边更舒展
      axisLabel: { color: CHROME.muted, fontFamily: FONT_FAMILY, hideOverlap: true },
      axisLine: { lineStyle: { color: CHROME.axis } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: CHROME.muted, fontFamily: FONT_FAMILY },
      // 折线图去掉网格线更干净；柱状图保留极淡虚线定位
      splitLine:
        type === 'line'
          ? { show: false }
          : { lineStyle: { color: CHROME.gridline, type: 'dashed' } },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series,
  }
}
