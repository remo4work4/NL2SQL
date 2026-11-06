"""FastAPI 应用入口。"""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, chat, db, health, sessions
from app.core.config import settings
from app.core.database import init_app_db

logger = logging.getLogger("nl2sql")


def _setup_logging() -> None:
    """控制台 + 滚动文件日志（NFR-4 结构化日志，含 request_id）。"""
    log_dir = Path(settings.app_db_file).parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时初始化日志与元数据库（建表 + 预置管理员账号）。"""
    _setup_logging()
    init_app_db()  # 应用表 + 语义元数据表 + 限流表（Phase 9 全部在 PG）
    logger.info("服务启动: %s v%s", settings.app_name, settings.version)
    yield


app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(db.router)
app.include_router(chat.router)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """每个请求分配 request_id 并记录耗时（NFR-4）。"""
    request_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    resp = await call_next(request)
    logger.info(
        "[%s] %s %s -> %s (%.0fms)",
        request_id,
        request.method,
        request.url.path,
        resp.status_code,
        (time.perf_counter() - t0) * 1000,
    )
    return resp


@app.get("/")
def root() -> dict:
    """服务信息。"""
    return {"service": "nl2sql-backend", "docs": "/docs", "health": "/api/health"}
