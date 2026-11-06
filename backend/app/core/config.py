"""全局配置模块。

所有可配置项集中于此，通过环境变量或 backend/.env 覆盖。
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 若运行环境配置了系统代理（如 Windows 注册表 WinINET 代理），httpx/urllib 的
# trust_env 会把 127.0.0.1 也送进代理导致 502（chroma 客户端实测）。
# 补 NO_PROXY 绕过回环地址；外部域名（百炼 API 等）仍按原样走代理。
os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,0.0.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/


class Settings(BaseSettings):
    """应用配置。字段名与环境变量一一对应（不区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "NL2SQL 智能数据分析系统"
    version: str = "0.2.0"

    # 阿里云百炼（DashScope）Qwen3
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # qwen3.8-max：百炼当前旗舰文本模型（Qwen3 家族）；备选 qwen-max 别名 / qwen-plus 低成本档
    llm_model: str = "qwen3.8-max"
    llm_temperature: float = 0.1
    llm_timeout: int = 60
    llm_enable_thinking: bool = False  # 需求文档风险应对：默认关闭思考模式以降低延迟

    # 服务与安全（默认端口：后端 8001、前端 5174，可按需调整）
    cors_origins: list[str] = ["http://localhost:5174"]
    memory_window: int = 6          # 上下文记忆窗口（轮数，FR-6）
    max_result_rows: int = 500      # 查询结果行数上限（FR-3/4）
    token_ttl_hours: int = 24       # 登录 token 有效期（FR-15）
    sql_retry_times: int = 1        # SQL 执行失败自动修正次数（FR-10）
    sql_timeout: float = 5.0        # SQL 执行超时秒数（FR-4）
    max_concurrent_llm: int = 2     # 令牌桶容量 = 全局并发 LLM 上限（Phase 8 起跨进程共享）
    llm_rate_per_second: float = 2.0  # 令牌桶补充速率（tokens/s，全局）
    log_level: str = "INFO"         # 日志级别（NFR-4 可维护性）

    # ---- Phase 8 多进程：共享限流后端 ----
    # redis_url 为空时用 SQLite 共享令牌桶（app.db，跨进程原子）；
    # 配置后切换 Redis 令牌桶（Phase 9 多实例必须），如 redis://127.0.0.1:6379/0
    redis_url: str = ""

    # 预置管理员账号（登录种子数据）
    admin_username: str = "admin"
    admin_password: str = "admin123"

    # 数据库路径（相对 backend/ 目录，Phase 9 起 PostgreSQL 为主存储，SQLite 仅历史遗留）
    business_db_path: str = "data/business.db"
    app_db_path: str = "data/app.db"

    # ---- Phase 9 多实例：PostgreSQL ----
    # 注：以下 DSN 内的账号密码为本地开发/测试默认值，生产环境必须通过环境变量覆盖
    pg_dsn: str = "postgresql://nl2sql:nl2sql@127.0.0.1:5433/nl2sql"  # 应用数据（读写）
    pg_business_dsn: str = "postgresql://nl2sql_ro:nl2sql_ro@127.0.0.1:5433/nl2sql"  # 业务查询（只读角色）
    pg_admin_dsn: str = "postgresql://postgres:nl2sqlpg@127.0.0.1:5433/postgres"  # 管理员（测试建库用）
    chroma_mode: str = "embedded"       # embedded | server（多实例部署用 server）
    chroma_host: str = "127.0.0.1"
    chroma_port: int = 8002
    model_service_url: str = ""         # 模型服务（空 = 进程内加载；多实例部署用独立服务）
    schema_cache_ttl: int = 10          # PG schema 摘要缓存秒数（多实例无文件 mtime）

    # ---- RAG 语义检索（Phase 6 方案 B；双路+RRF+重排为 Phase 6 增强）----
    rag_enabled: bool = True          # 总开关；关闭时全量注入（改造前行为）
    rag_candidate_k: int = 10         # 向量/BM25 各路候选数（RRF 融合前）
    rag_top_k: int = 8                # RRF 融合后进入交叉编码器重排的候选数
    rag_max_tables: int = 6           # 注入上限（含 JOIN 闭包）
    rag_score_threshold: float = 0.25 # 向量路余弦相似度阈值，全丢时兜底全量注入
    rag_keyword_boost: bool = True    # 表/字段业务名精确命中兜底（作为 RRF 第三路）
    rag_bm25_enabled: bool = True     # BM25 词法路（jieba 分词，RRF 融合）
    rag_rerank_enabled: bool = True   # 交叉编码器重排序（RRF 之后）
    rag_rerank_threshold: float = 0.0 # 重排分数下限；全部不达标时回退 RRF 排序
    bge_model: str = "BAAI/bge-m3"    # 本地目录缺失时按此 ID 下载
    bge_model_dir: str = "models/bge-m3"  # 本地 BGE 模型目录（相对 backend/）
    torch_threads: int = 4            # 每 worker torch 推理线程数（Phase 8 多进程防 CPU 打满）
    reranker_model: str = "BAAI/bge-reranker-v2-m3"       # 重排序交叉编码器
    reranker_model_dir: str = "models/bge-reranker-v2-m3"  # 本地重排模型目录
    chroma_dir: str = "data/chroma"       # Chroma 持久化目录（相对 backend/）
    metadata_file: str = "data/metadata.json"        # 已复核的语义元数据（seed 源）
    metadata_draft_file: str = "data/metadata.draft.json"  # Qwen 生成草稿（待复核）
    hf_endpoint: str = "https://hf-mirror.com"  # 模型下载镜像（BGE 首次下载用）

    @property
    def business_db_file(self) -> Path:
        return BASE_DIR / self.business_db_path

    @property
    def app_db_file(self) -> Path:
        return BASE_DIR / self.app_db_path

    @property
    def bge_model_dir_file(self) -> Path:
        return BASE_DIR / self.bge_model_dir

    @property
    def reranker_model_dir_file(self) -> Path:
        return BASE_DIR / self.reranker_model_dir

    @property
    def chroma_dir_file(self) -> Path:
        return BASE_DIR / self.chroma_dir

    @property
    def metadata_file_path(self) -> Path:
        return BASE_DIR / self.metadata_file

    @property
    def metadata_draft_file_path(self) -> Path:
        return BASE_DIR / self.metadata_draft_file


settings = Settings()
