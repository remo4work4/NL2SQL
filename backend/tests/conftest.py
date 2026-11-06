"""测试夹具（Phase 9）：独立测试库 nl2sql_test（PostgreSQL），每测试清空重建。

前置：PostgreSQL 运行中（默认 127.0.0.1:5433），角色 nl2sql /
nl2sql_ro / 测试库由本夹具自动创建（幂等）。
"""
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.core import database, rate_limit
from app.core.config import settings
from scripts.seed_business import seed_business

TEST_DSN = "postgresql://nl2sql:nl2sql@127.0.0.1:5433/nl2sql_test"
TEST_RO_DSN = "postgresql://nl2sql_ro:nl2sql_ro@127.0.0.1:5433/nl2sql_test"

TRUNCATE_TABLES = [
    "messages", "sessions", "tokens", "users",
    "table_relations", "column_meta", "table_meta", "llm_limiter",
]


@pytest.fixture(scope="session", autouse=True)
def pg_test_db():
    """建测试库（幂等）并授权只读角色连接。"""
    admin = psycopg.connect(settings.pg_admin_dsn, autocommit=True)
    try:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'nl2sql_test'"
        ).fetchone()
        if not exists:
            admin.execute("CREATE DATABASE nl2sql_test OWNER nl2sql")
        admin.execute("GRANT CONNECT ON DATABASE nl2sql_test TO nl2sql_ro")
    finally:
        admin.close()
    yield


@pytest.fixture()
def db_paths(pg_test_db, monkeypatch):
    """把配置指向测试库，清空全部表，重建 app 表 + 预置 admin + 小规模业务数据。"""
    monkeypatch.setattr(settings, "pg_dsn", TEST_DSN)
    monkeypatch.setattr(settings, "pg_business_dsn", TEST_RO_DSN)

    database.init_app_db()  # 先建表（幂等），确保 TRUNCATE 目标存在

    conn = psycopg.connect(TEST_DSN, autocommit=True)
    try:
        for t in TRUNCATE_TABLES:
            conn.execute(f"TRUNCATE {t} CASCADE")
    finally:
        conn.close()

    database.init_app_db()  # 重新预置管理员账号
    seed_business(None, n_customers=10, n_products=12, n_orders=300, random_seed=7, engine="pg")

    # 重置进程内缓存（限流后端 / schema 摘要）
    rate_limit.reset_backends()
    from app.services import chat_service

    chat_service._schema_cache = {"ts": 0.0, "details": {}}
    return {"pg_dsn": TEST_DSN}


@pytest.fixture()
def client(db_paths):
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    """登录预置管理员，返回带 Bearer token 的请求头。"""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}
