/** 轻量 ECharts 封装：按需引入（bar/line/pie + 网格/图例/提示 + Canvas 渲染），初始化、更新、自适应尺寸。 */
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption } from 'echarts/core'
import { useEffect, useRef } from 'react'
import type { CSSProperties } from 'react'
import type { EChartsOption } from 'echarts'

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
])

interface EChartProps {
  option: EChartsOption
  style?: CSSProperties
}

export default function EChart({ option, style }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const chart = echarts.init(el)
    chartRef.current = chart
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(el)
    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    chartRef.current?.setOption(option as unknown as EChartsCoreOption, true)
  }, [option])

  return <div ref={containerRef} style={{ width: '100%', height: '100%', minHeight: 200, ...style }} />
}
