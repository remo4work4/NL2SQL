/** 图表调色板与 chrome（dataviz 参考调色板·暗色档，已针对暗色表面通过 CVD/对比度校验）。 */

/** 分类色固定顺序（勿循环取色，超过 8 类应归入"其他"） */
export const CATEGORICAL = [
  '#3987e5', // 1 blue
  '#d95926', // 2 orange
  '#199e70', // 3 aqua
  '#c98500', // 4 yellow
  '#d55181', // 5 magenta
  '#008300', // 6 green
  '#9085e9', // 7 violet
  '#e66767', // 8 red
]

export const CHROME = {
  inkPrimary: '#f0efec',
  inkSecondary: '#c3c2b7',
  muted: '#898781',
  gridline: '#2c2c2a',
  axis: '#383835',
  surface: '#1a1a19',
}

export const FONT_FAMILY =
  "-apple-system, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif"
