import { describe, expect, it } from 'vitest'
import type { QueryResult } from '../api/types'
import { inferChartSpec } from './chartInfer'

const mk = (columns: string[], rows: (string | number)[][]): QueryResult => ({
  columns,
  rows,
  row_count: rows.length,
  truncated: false,
})

describe('inferChartSpec 兜底推断（FR-7）', () => {
  it('日期 + 数值 → 折线图', () => {
    const spec = inferChartSpec(
      mk(['month', 'sales'], [['2025-01', 82.4], ['2025-02', 61.8]]),
    )
    expect(spec?.chart_type).toBe('line')
  })

  it('分类 + 数值 → 柱状图', () => {
    const spec = inferChartSpec(
      mk(['region', 'sales'], [['华东', 428.6], ['华北', 302.4]]),
    )
    expect(spec?.chart_type).toBe('bar')
  })

  it('占比类（总和≈100）→ 饼图', () => {
    const spec = inferChartSpec(
      mk(['category', 'share'], [['A', 55], ['B', 30], ['C', 15]]),
    )
    expect(spec?.chart_type).toBe('pie')
  })

  it('无数值列 → null（仅表格）', () => {
    expect(inferChartSpec(mk(['a', 'b'], [['x', 'y']]))).toBeNull()
  })

  it('空结果 → null', () => {
    expect(inferChartSpec(mk(['a', 'b'], []))).toBeNull()
  })
})
