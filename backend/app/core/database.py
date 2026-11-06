"""PostgreSQL 连接管理（Phase 9：多实例共享存储）。

- connect_db()：应用数据读写连接（users/sessions/messages/tokens/
  语义元数据/限流表），角色 nl2sql_app（owner）
- connect_business_db()：业务数据只读连接（角色 nl2sql_ro，仅 SELECT 授权，
  等价于 Phase 8 之前 SQLite mode=ro 的安全兜底）
"""
import uuid

import psycopg
from psycopg.rows import dict_row

from app.core import security
from app.core.config import settings

APP_DB_DDL = [
    """CREATE TABLE IF NOT EXISTS users (
      id            TEXT PRIMARY KEY,
      username      TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      created_at    TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
      id          TEXT PRIMARY KEY,
      user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      title       TEXT NOT NULL,
      created_at  TEXT NOT NULL,
      updated_at  TEXT NOT NULL,
      seq         BIGSERIAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at DESC)",
    """CREATE TABLE IF NOT EXISTS messages (
      id          TEXT PRIMARY KEY,
      session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
      role        TEXT NOT NULL,
      content     TEXT NOT NULL,
      sql         TEXT,
      chart_spec  TEXT,
      result      TEXT,
      status      TEXT NOT NULL DEFAULT 'done',
      error       TEXT,
      created_at  TEXT NOT NULL,
      seq         BIGSERIAL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq)",
    """CREATE TABLE IF NOT EXISTS tokens (
      token       TEXT PRIMARY KEY,
      username    TEXT NOT NULL,
      created_at  TEXT NOT NULL,
      expires_at  TEXT NOT NULL
    )""",
]

# 语义元数据表（Phase 6）+ 限流表（Phase 8），一并迁入 PG
SEMANTIC_DDL = [
    """CREATE TABLE IF NOT EXISTS table_meta (
      table_name  TEXT PRIMARY KEY,
      biz_name    TEXT NOT NULL,
      description TEXT NOT NULL,
      updated_at  TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS column_meta (
      table_name  TEXT NOT NULL REFERENCES table_meta(table_name) ON DELETE CASCADE,
      column_name TEXT NOT NULL,
      biz_name    TEXT NOT NULL,
      description TEXT NOT NULL,
      enum_values TEXT NOT NULL DEFAULT '[]',
      updated_at  TEXT NOT NULL,
      PRIMARY KEY (table_name, column_name)
    )""",
    """CREATE TABLE IF NOT EXISTS table_relations (
      id          BIGSERIAL PRIMARY KEY,
      from_table  TEXT NOT NULL,
      from_column TEXT NOT NULL,
      to_table    TEXT NOT NULL,
      to_column   TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      UNIQUE (from_table, from_column, to_table, to_column)
    )""",
    """CREATE TABLE IF NOT EXISTS llm_limiter (
      key      TEXT PRIMARY KEY,
      tokens   DOUBLE PRECISION NOT NULL,
      ts       DOUBLE PRECISION NOT NULL,
      inflight INTEGER NOT NULL DEFAULT 0,
      taken    INTEGER NOT NULL DEFAULT 0
    )""",
]


def connect_db() -> psycopg.Connection:
    """应用数据读写连接（autocommit 关闭，调用方显式 commit）。"""
    return psycopg.connect(settings.pg_dsn, row_factory=dict_row)


def connect_business_db() -> psycopg.Connection:
    """业务数据只读连接（nl2sql_ro 角色，SELECT-only 授权兜底）。"""
    return psycopg.connect(settings.pg_business_dsn, row_factory=dict_row)


def init_app_db() -> None:
    """建表并预置管理员账号（幂等，应用启动时调用）。"""
    conn = connect_db()
    try:
        for ddl in APP_DB_DDL + SEMANTIC_DDL:
            conn.execute(ddl)
        cur = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE username = %s", (settings.admin_username,)
        )
        if cur.fetchone()["n"] == 0:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (%s, %s, %s, %s)",
                (
                    str(uuid.uuid4()),
                    settings.admin_username,
                    security.hash_password(settings.admin_password),
                    security.utc_now(),
                ),
            )
        conn.commit()
    finally:
        conn.close()
