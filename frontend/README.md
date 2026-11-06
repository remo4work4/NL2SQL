# NL2SQL 前端

React 19 + TypeScript + Ant Design + ECharts + zustand，Vite 构建。三栏布局：会话列表 / 对话消息流（解读 + SQL + 结果表）/ 图表区（柱状/折线/饼图/表格切换）。

## 运行

```bash
npm install
cp .env.example .env.local    # 连接真实后端时设 VITE_USE_MOCK=false
npm run dev
```

`.env.example` 说明：

- `VITE_API_BASE_URL`：后端地址（默认 http://localhost:8001）
- `VITE_USE_MOCK`：`true` 纯前端 mock 演示；`false` 直连真实后端

## 测试

```bash
npm test        # vitest
npx tsc -b      # 类型检查
```

目录说明：`src/api/`（接口封装 + mock 层）、`src/store/`（zustand 状态）、`src/components/`（UI 组件）、`src/pages/`（登录页）、`src/utils/`（图表推断与配色）。
