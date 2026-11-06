"""健康检查接口。"""
from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check() -> dict:
    """服务健康检查（Phase 0 验收用）。"""
    return {
        "status": "ok",
        "service": "nl2sql-backend",
        "version": settings.version,
    }
