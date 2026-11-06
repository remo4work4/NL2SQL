# NL2SQL 智能数据分析系统

以自然语言为入口的一站式数据分析系统：提问 → 自动生成 SQL → 执行查询 → 图表渲染与解读。面向「会业务、不会 SQL」的分析人员，把从提问到看图的全过程收敛到一次对话中。

## 核心能力

- **NL→SQL 生成与展示**：自然语言自动生成 SQL（PostgreSQL 方言），代码块展示、一键复制
- **RAG 语义检索**：BGE 向量 + BM25 双路召回 → RRF 融合 → 交叉编码器重排序，表数量增长后仍按需注入 schema
- **语义元数据治理**：表/字段中文业务名、枚举值、JOIN 关系集中管理，Qwen 辅助生成草稿 + 人工复核流程
- **意图识别**：规则快路径（写操作/闲聊零 LLM 成本拦截）+ LLM 结构化意图，四类意图正确路由
- **多轮对话**：滑动窗口上下文记忆，支持指代追问（「那按地区再看一下」）
- **智能可视化**：柱状/折线/饼图自动推断 + 手动切换 + 表格视图
- **多用户体系**：注册/登录、会话与消息按用户隔离（他人会话一律不可见）
- **企业级安全**：只读角色查询兜底 + SQL 白名单 + 行数上限 + 执行超时，四层防护
- **多实例部署**：PostgreSQL + Redis + Chroma server + 模型服务，跨实例共享配额与数据

## 架构

```
浏览器（React 前端）
   │ SSE 流式
API 实例 × N（FastAPI）── Redis（跨实例限流，令牌桶+在途计数）
   │            ├── 模型服务（BGE 稠密 + 交叉编码器，独立进程共享一份）
   │            └── Chroma server（向量索引）
   ├── PostgreSQL（应用库 + 业务库；业务查询走只读角色）
   └── Qwen3 大模型（阿里云百炼，生成 SQL 与解读）
```

RAG 链路：提问 → 三路召回（稠密向量 + BM25 词法 + 业务名精确命中）→ RRF 融合 → 重排序 → JOIN 闭包 → 按需注入语义化 schema → 生成 SQL。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / PostgreSQL 17 / Redis / Chroma / LangChain |
| 前端 | React 19 / TypeScript / Ant Design / ECharts / zustand / Vite |
| 模型 | Qwen3（百炼 API）；BGE bge-m3 + bge-reranker-v2-m3（本地） |
| 部署 | Docker Compose（多实例编排） |

## 目录结构

```
NL2SQL/
├── backend/
│   ├── app/
│   │   ├── main.py          # 应用入口
│   │   ├── modelsvc.py      # 模型服务（多实例共享 BGE/重排模型）
│   │   ├── core/            # 配置 / PG 连接 / 限流 / SQL 安全 / 语义元数据 / RAG 检索
│   │   ├── api/             # 路由（认证/会话/对话 SSE/表结构）
│   │   ├── services/        # 会话 / 认证 / 对话编排
│   │   ├── agent/           # NL2SQL 管道 / 提示词 / 意图识别
│   │   ├── llm/             # Qwen 接入
│   │   └── schemas/         # Pydantic 模型
│   ├── scripts/             # 种子数据 / 元数据生成与复核 / 验收脚本
│   ├── tests/               # pytest（107 用例）
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                # React 前端
├── docker-compose.yml       # 多实例编排（api×N + postgres + redis + chroma + modelsvc）
├── 需求文档.md               # 功能/非功能需求、接口协议、验收标准（附录 A~D）
├── 验收报告.md               # Phase 4/6/7/8/9 验收记录
└── report.md                # 技术选型调研报告
```

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
# 前置：安装 Docker；准备 DASHSCOPE_API_KEY；下载 BGE 模型到 backend/models/
docker compose up -d
# 访问 http://localhost:5174（前端），http://localhost:8001（API）
```

### 方式二：原生进程

```bash
# 1. 基础设施：PostgreSQL（创建角色 nl2sql / nl2sql_ro 与数据库 nl2sql）、
#    Redis、Chroma server（chroma run --path data/chroma --port 8002）
# 2. 后端依赖与配置
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
cp .env.example .env                                                    # 填入 DASHSCOPE_API_KEY
# 3. 数据与语义元数据
.venv/Scripts/python scripts/seed_business.py --force     # 业务示例数据入 PG
.venv/Scripts/python scripts/generate_metadata.py         # Qwen 生成语义元数据草稿
#    人工复核 data/metadata.draft.json 后保存为 data/metadata.json
.venv/Scripts/python scripts/seed_metadata.py             # 写入 PG + 重建向量索引
# 4. 启动（多实例部署时模型服务独立启动）
.venv/Scripts/python -m uvicorn app.modelsvc:app --port 8004
.venv/Scripts/python -m uvicorn app.main:app --port 8001
# 5. 前端
cd ../frontend && npm install && cp .env.example .env.local
#    .env.local 中设 VITE_USE_MOCK=false 后：
npm run dev
```

访问 http://localhost:5174，预置账号 `admin / admin123`（`.env` 可改）。

## 关键配置（backend/.env）

| 变量 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key（必填） |
| `LLM_MODEL` | 默认 `qwen3.8-max`，可切换 qwen-max/qwen-plus |
| `PG_DSN` / `PG_BUSINESS_DSN` | 应用库（读写）/ 业务库（只读角色）连接串 |
| `REDIS_URL` | 共享限流 Redis；为空时降级 PG 后端 |
| `CHROMA_MODE` | `embedded`（单机）/ `server`（多实例） |
| `MODEL_SERVICE_URL` | 模型服务地址；为空时进程内加载模型 |
| `RAG_*` | 检索参数：候选数 / 重排池 / 阈值 / 注入上限 |
| `MAX_CONCURRENT_LLM` / `LLM_RATE_PER_SECOND` | 全局限流：并发上限 / 令牌补充速率 |

完整配置项见 [backend/.env.example](backend/.env.example)。

## 语义元数据运维

业务库 schema 变更后的标准流程：

1. `scripts/generate_metadata.py` —— Qwen 从物理结构 + 取值样本生成草稿（含覆盖率与枚举完备性校验）
2. 人工复核 `data/metadata.draft.json`（业务名/描述/枚举/关联），保存为 `data/metadata.json`
3. `scripts/seed_metadata.py` —— 写入 PostgreSQL + 重建 Chroma 索引

## 测试与验收

```bash
cd backend && .venv/Scripts/python -m pytest tests/       # 107 用例（需本地 PG）
.venv/Scripts/python scripts/test_acceptance.py           # 附录 A：10 问端到端（需服务运行）
.venv/Scripts/python scripts/eval_rag.py                  # 附录 C：召回/排序/延迟
.venv/Scripts/python scripts/test_concurrency.py          # 并发压测 + 限流证据
```

验收基准（详见需求文档附录）：附录 A 标准问句 SQL 成功率 ≥ 80%；附录 B 恶意 SQL 全拦截；附录 C 召回命中率 ≥ 90%；附录 D 意图路由全正确。

## 多实例部署

- 数据层共享：PostgreSQL（应用 + 业务）+ Redis（限流）+ Chroma server（向量索引）
- 模型共享：模型服务独立进程，所有 API 实例经 `MODEL_SERVICE_URL` 调用
- 实例间无本地状态；限流配额全局一致（Redis 令牌桶 + 在途计数）
- 启动：`docker compose up -d` 或按上文原生进程方式起多个 `uvicorn app.main:app` 实例

## 开发阶段

需求与验收全流程见 [需求文档.md](需求文档.md)（FR-1~21、接口协议、附录 A~D）与 [验收报告.md](验收报告.md)；技术选型依据见 [report.md](report.md)。主要阶段：

| 阶段 | 内容 |
|---|---|
| Phase 0~4 | 前后端框架、NL2SQL 管道、四层安全、会话/登录、可视化、联调加固 |
| Phase 6 | RAG 语义检索（双路召回 + RRF + 重排）与语义元数据治理 |
| Phase 7 | 提问意图识别（规则快路径 + LLM 结构化意图） |
| Phase 8 | 单机多进程（Redis 共享限流、SQLite WAL、并发加固） |
| Phase 9 | 多实例 + PostgreSQL + 多用户体系 |
