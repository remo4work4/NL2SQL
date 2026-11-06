/** 图表兜底推断规则（FR-7）：LLM 未给出图表规格时，按数据形状推断。 */
import type { ChartSpec, QueryResult } from '../api/types'

const DATE_PATTERN = /^\d{4}[-/年]|月|季度|周|week|month|date|day|日期|时间/i

function isNumeric(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

function columnIsNumeric(result: QueryResult, col: string): boolean {
  const idx = result.columns.indexOf(col)
  if (idx < 0) return false
  return result.rows.some((r) => isNumeric(r[idx]))
}

function looksLikeDate(values: unknown[]): boolean {
  return values.some((v) => typeof v === 'string' && DATE_PATTERN.test(v))
}

/**
 * 推断规则：
 * - 分类列 + 数值列 → 柱状图；x 列像日期 → 折线图
 * - 占比类（数值全在 [0,1]，或总和≈100）且类别 ≤10 → 饼图
 * - 无数值列或无数据 → null（仅展示表格）
 */
export function inferChartSpec(result: QueryResult): ChartSpec | null {
  const { columns, rows } = result
  if (columns.length < 2 || rows.length === 0) return null

  const numericCols = columns.filter((c) => columnIsNumeric(result, c))
  if (numericCols.length === 0) return null

  const xCol = columns.find((c) => !numericCols.includes(c)) ?? columns[0]
  const yCols = numericCols.filter((c) => c !== xCol).slice(0, 2)
  if (yCols.length === 0) return null

  if (yCols.length === 1) {
    const yIdx = columns.indexOf(yCols[0])
    const values = rows.map((r) => r[yIdx]).filter(isNumeric)
    if (values.length > 0 && values.length <= 10) {
      const sum = values.reduce((a, b) => a + b, 0)
      const allRatio = values.every((v) => v >= 0 && v <= 1)
      if (allRatio || Math.abs(sum - 100) < 1) {
        return { chart_type: 'pie', x: xCol, y: yCols }
      }
    }
  }

  const xIdx = columns.indexOf(xCol)
  const chartType = looksLikeDate(rows.map((r) => r[xIdx])) ? 'line' : 'bar'
  return { chart_type: chartType, x: xCol, y: yCols }
}
