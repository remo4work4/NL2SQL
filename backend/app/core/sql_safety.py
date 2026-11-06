"""SQL 安全防护（FR-3/4，Phase 9 PostgreSQL）：

1. 业务查询走 nl2sql_ro 只读角色连接（仅 SELECT 授权，数据库层兜底）
2. 白名单校验：仅单条 SELECT/WITH 查询，拒绝写操作关键字
3. 行数上限：无 LIMIT 时自动补 LIMIT（fetch 层再兜底截断）
4. 执行超时：PG 服务端 statement_timeout（无需 SQLite 时代的线程中断 hack）
"""
import re

import psycopg
import sqlparse
from sqlparse import tokens as T

from app.core.database import connect_business_db

# 禁用关键字（写操作与危险语句；recursive 防递归 CTE 计算炸弹）
FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "attach", "detach",
    "pragma", "vacuum", "reindex", "replace", "truncate", "grant", "revoke",
    "begin", "commit", "rollback", "savepoint", "transaction", "recursive",
}

MAX_SQL_LENGTH = 4000


class SQLUnsafeError(Exception):
    """SQL 未通过安全校验。"""


class SQLExecutionError(Exception):
    """SQL 执行失败。"""


def validate_sql(sql: str, max_rows: int = 500) -> str:
    """校验并返回安全的 SQL（必要时追加 LIMIT）。

    抛 SQLUnsafeError：多语句、非查询语句、含禁用关键字、超长。
    """
    sql_clean = sqlparse.format(sql, strip_comments=True).strip()
    if not sql_clean:
        raise SQLUnsafeError("SQL 为空")
    if len(sql_clean) > MAX_SQL_LENGTH:
        raise SQLUnsafeError("SQL 超长")

    statements = [s for s in sqlparse.parse(sql_clean) if str(s).strip()]
    if len(statements) != 1:
        raise SQLUnsafeError("仅允许单条查询语句（检测到多语句）")

    stmt = statements[0]
    stype = stmt.get_type().upper()
    if stype not in ("SELECT", "UNKNOWN"):
        raise SQLUnsafeError(f"仅允许 SELECT 查询，不允许 {stype}")
    if stype == "UNKNOWN" and not re.search(r"\bselect\b", sql_clean, re.IGNORECASE):
        raise SQLUnsafeError("仅允许 SELECT 查询")

    # 关键字白名单：仅检查关键字 token（字符串字面量与列名不会被误伤）
    for tok in stmt.flatten():
        if tok.ttype in T.Keyword and tok.value.lower() in FORBIDDEN_KEYWORDS:
            raise SQLUnsafeError(f"检测到禁止的关键字: {tok.value}")

    # 行数上限保护
    if not re.search(r"\blimit\b", sql_clean, re.IGNORECASE):
        sql_clean = f"{sql_clean} LIMIT {max_rows}"
    return sql_clean


def execute_query(sql: str, max_rows: int = 500, timeout: float = 5.0) -> dict:
    """在只读业务库（nl2sql_ro）上执行 SQL，返回 {columns, rows, row_count, truncated}。

    抛 SQLExecutionError：执行失败或超时（PG statement_timeout 服务端兜底）。
    """
    # 参数化不可行（动态 SQL），超时与权限交给服务端：只读角色 + statement_timeout
    import psycopg
    from psycopg.rows import dict_row

    dsn = _ro_dsn_with_timeout(timeout)
    conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description:
                columns = [d.name for d in cur.description]
                rows = [[_jsonable(v) for v in r.values()] for r in cur.fetchmany(max_rows + 1)]
            else:
                columns, rows = [], []
            truncated = len(rows) > max_rows
            return {
                "columns": columns,
                "rows": rows[:max_rows] if truncated else rows,
                "row_count": len(rows) if not truncated else max_rows,
                "truncated": truncated,
            }
    except psycopg.errors.QueryCanceled as e:  # statement_timeout
        raise SQLExecutionError(f"查询执行超时（>{timeout:.0f}s）") from e
    except psycopg.Error as e:
        raise SQLExecutionError(str(e).split("\n")[0][:200]) from e
    finally:
        conn.close()


def _jsonable(v):
    """PG 返回类型 → JSON 可序列化（numeric→float、date→iso 字符串）。"""
    import datetime
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime.date, datetime.datetime, datetime.time)):
        return v.isoformat()
    return v


def _ro_dsn_with_timeout(timeout: float) -> str:
    """在 DSN 上附加 statement_timeout（毫秒）。"""
    from app.core.config import settings

    dsn = settings.pg_business_dsn
    sep = "&" if "?" in dsn else "?"
    return f"{dsn}{sep}options=-c%20statement_timeout%3D{int(timeout * 1000)}"
