"""会话管理服务（FR-8/9/12 + FR-21 用户隔离）：sessions/messages CRUD。

Phase 9：全部查询带 user_id 过滤——会话/消息仅本人可见可操作，
他人会话一律视为不存在（404），不泄露存在性。
"""
import json
import uuid

from app.core import security
from app.core.database import connect_db


def _convert_message(row) -> dict:
    """DB 行 → 前端协议格式（sql/chart_spec/result 由 JSON 文本转对象）。"""
    def loads(v):
        if not v:
            return None
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return None

    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "role": row["role"],
        "content": row["content"],
        "sql": row["sql"],
        "chart_spec": loads(row["chart_spec"]),
        "result": loads(row["result"]),
        "status": row["status"],
        "error": row["error"],
        "created_at": row["created_at"],
    }


def _session_row(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_session(user_id: str, title: str = "新会话") -> dict:
    conn = connect_db()
    try:
        now = security.utc_now()
        sid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO sessions (id, user_id, title, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
            (sid, user_id, title, now, now),
        )
        conn.commit()
        return {"id": sid, "title": title, "created_at": now, "updated_at": now}
    finally:
        conn.close()


def list_sessions(user_id: str) -> list[dict]:
    conn = connect_db()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE user_id = %s ORDER BY updated_at DESC, seq DESC",
            (user_id,),
        ).fetchall()
        return [_session_row(r) for r in rows]
    finally:
        conn.close()


def get_session(user_id: str, session_id: str) -> dict | None:
    conn = connect_db()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = %s AND user_id = %s", (session_id, user_id)
        ).fetchone()
        return _session_row(row) if row else None
    finally:
        conn.close()


def get_messages(user_id: str, session_id: str) -> list[dict]:
    conn = connect_db()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = %s AND session_id IN "
            "(SELECT id FROM sessions WHERE id = %s AND user_id = %s) ORDER BY seq",
            (session_id, session_id, user_id),
        ).fetchall()
        return [_convert_message(r) for r in rows]
    finally:
        conn.close()


def get_recent_messages(user_id: str, session_id: str, limit: int, exclude_id: str | None = None) -> list[dict]:
    """最近 limit 条消息（正序返回），可排除刚插入的用户消息。"""
    conn = connect_db()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = %s AND id != %s "
            "AND session_id IN (SELECT id FROM sessions WHERE id = %s AND user_id = %s) "
            "ORDER BY seq DESC LIMIT %s",
            (session_id, exclude_id or "", session_id, user_id, limit),
        ).fetchall()
        rows.reverse()
        return [_convert_message(r) for r in rows]
    finally:
        conn.close()


def add_message(
    user_id: str,
    session_id: str,
    role: str,
    content: str,
    sql: str | None = None,
    chart: dict | None = None,
    result: dict | None = None,
    status: str = "done",
    error: str | None = None,
) -> str:
    """追加消息并返回消息 id（会话不属于该用户时抛 KeyError 由调用方处理）。"""
    conn = connect_db()
    try:
        own = conn.execute(
            "SELECT 1 FROM sessions WHERE id = %s AND user_id = %s", (session_id, user_id)
        ).fetchone()
        if not own:
            raise KeyError(session_id)
        mid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO messages (id, session_id, role, content, sql, chart_spec, result, status, error, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                mid,
                session_id,
                role,
                content,
                sql,
                json.dumps(chart, ensure_ascii=False) if chart else None,
                json.dumps(result, ensure_ascii=False) if result else None,
                status,
                error,
                security.utc_now(),
            ),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = %s WHERE id = %s", (security.utc_now(), session_id)
        )
        conn.commit()
        return mid
    finally:
        conn.close()


def rename_session(user_id: str, session_id: str, title: str) -> bool:
    conn = connect_db()
    try:
        cur = conn.execute(
            "UPDATE sessions SET title = %s, updated_at = %s WHERE id = %s AND user_id = %s",
            (title, security.utc_now(), session_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_session(user_id: str, session_id: str) -> bool:
    conn = connect_db()
    try:
        cur = conn.execute(
            "DELETE FROM sessions WHERE id = %s AND user_id = %s", (session_id, user_id)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
