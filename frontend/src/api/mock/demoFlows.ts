/** mock 演示问答流程：销售主题 4 组 + 1 组安全拦截场景。 */
import type { ChartSpec, QueryResult } from '../types'

export interface DemoFlow {
  answer: string
  sql: string
  result: QueryResult
  chart: ChartSpec
}

export interface DemoError {
  error: { code: string; message: string }
}

/** 流程一：月度销售趋势（折线图） */
export const monthlyTrend: DemoFlow = {
  answer:
    '2025 年全年销售额合计 1,332.6 万元，12 月达到峰值 156.3 万元，2 月为全年低谷 61.8 万元；下半年整体高于上半年，第四季度受大促拉动明显。',
  sql: "SELECT strftime('%Y-%m', order_date) AS month, SUM(amount) AS sales\nFROM orders\nWHERE order_date >= '2025-01-01' AND order_date < '2026-01-01'\nGROUP BY month\nORDER BY month",
  result: {
    columns: ['month', 'sales'],
    rows: [
      ['2025-01', 82.4],
      ['2025-02', 61.8],
      ['2025-03', 88.5],
      ['2025-04', 95.2],
      ['2025-05', 102.7],
      ['2025-06', 118.6],
      ['2025-07', 109.3],
      ['2025-08', 121.5],
      ['2025-09', 132.1],
      ['2025-10', 118.9],
      ['2025-11', 145.3],
      ['2025-12', 156.3],
    ],
    row_count: 12,
    truncated: false,
  },
  chart: { chart_type: 'line', title: '2025 年各月销售额趋势（万元）', x: 'month', y: ['sales'] },
}

/** 流程二：品类占比（饼图） */
export const categoryShare: DemoFlow = {
  answer: '销售额前三大品类为数码家电（386.5 万元）、服饰鞋包（318.2 万元）、食品生鲜（245.6 万元），合计占比 73.9%。',
  sql: 'SELECT p.category, SUM(o.amount) AS sales\nFROM orders o\nJOIN products p ON o.product_id = p.id\nWHERE o.order_date >= \'2025-01-01\'\nGROUP BY p.category\nORDER BY sales DESC',
  result: {
    columns: ['category', 'sales'],
    rows: [
      ['数码家电', 386.5],
      ['服饰鞋包', 318.2],
      ['食品生鲜', 245.6],
      ['家居日用', 198.4],
      ['美妆个护', 137.8],
    ],
    row_count: 5,
    truncated: false,
  },
  chart: { chart_type: 'pie', title: '各品类销售额占比（万元）', x: 'category', y: ['sales'] },
}

/** 流程三：地区对比（柱状图，通用兜底） */
export const regionCompare: DemoFlow = {
  answer: '华东以 428.6 万元领先（占 30.5%），华北、华南紧随其后；东北最低，为 96.7 万元。',
  sql: 'SELECT c.region, SUM(o.amount) AS sales\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nGROUP BY c.region\nORDER BY sales DESC',
  result: {
    columns: ['region', 'sales'],
    rows: [
      ['华东', 428.6],
      ['华北', 302.4],
      ['华南', 276.8],
      ['西南', 158.2],
      ['华中', 142.1],
      ['东北', 96.7],
    ],
    row_count: 6,
    truncated: false,
  },
  chart: { chart_type: 'bar', title: '各地区销售额对比（万元）', x: 'region', y: ['sales'] },
}

/** 流程四：客户等级平均消费 */
export const customerLevel: DemoFlow = {
  answer: '金牌客户平均消费 1,284.5 元，约为普通客户的 6 倍，高价值客户贡献显著，可针对金牌客户加强复购运营。',
  sql: 'SELECT c.level, AVG(o.amount) AS avg_amount\nFROM orders o\nJOIN customers c ON o.customer_id = c.id\nGROUP BY c.level\nORDER BY avg_amount DESC',
  result: {
    columns: ['level', 'avg_amount'],
    rows: [
      ['金牌', 1284.5],
      ['银牌', 736.2],
      ['普通', 214.8],
    ],
    row_count: 3,
    truncated: false,
  },
  chart: { chart_type: 'bar', title: '各客户等级平均消费金额（元）', x: 'level', y: ['avg_amount'] },
}

const ERROR_PATTERN = /删除|修改|更新|插入|新增|drop|delete|update|insert|alter/i

/** 按问题关键词路由到演示流程；写操作类问题返回安全拦截错误（附录 B 场景）。 */
export function routeDemoFlow(question: string): DemoFlow | DemoError {
  if (ERROR_PATTERN.test(question)) {
    return {
      error: {
        code: 'SQL_UNSAFE',
        message: '该查询不被允许：系统仅支持 SELECT 查询，不执行任何写操作。',
      },
    }
  }
  if (/品类|占比/.test(question)) return categoryShare
  if (/月|趋势/.test(question)) return monthlyTrend
  if (/地区|区域|城市|省份/.test(question)) return regionCompare
  if (/等级|客户|消费/.test(question)) return customerLevel
  return regionCompare
}
