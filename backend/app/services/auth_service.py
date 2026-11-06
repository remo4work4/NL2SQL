"""认证服务（FR-15/21）：登录签发 token、注册（Phase 9）、登出、token 校验。"""
import uuid
from datetime import datetime, timedelta, timezone

from app.core import security
from app.core.config import settings
from app.core.database import connect_db


class AuthError(Exception):
    """登录/注册失败（用户名或密码错误、用户名已存在等）。"""


def register_user(username: str, password: str) -> dict:
    """注册新用户（FR-21）：用户名唯一，成功后直接签发 token（免二次登录）。"""
    username = username.strip()
    if not username or len(username) < 2 or len(username) > 32:
        raise AuthError("用户名需为 2~32 个字符")
    if len(password) < 6:
        raise AuthError("密码至少 6 位")
    conn = connect_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = %s", (username,)
        ).fetchone()
        if exists:
            raise AuthError("用户名已存在")
        uid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, username, password_hash, created_at) VALUES (%s, %s, %s, %s)",
            (uid, username, security.hash_password(password), security.utc_now()),
        )
        conn.commit()
    finally:
        conn.close()
    return login_user(username, password)


def login_user(username: str, password: str) -> dict:
    conn = connect_db()
    try:
        row = conn.execute(
            "SELECT username, password_hash FROM users WHERE username = %s", (username,)
        ).fetchone()
        if row is None or not security.verify_password(password, row["password_hash"]):
            raise AuthError("用户名或密码错误")

        token = security.new_token()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=settings.token_ttl_hours)
        conn.execute(
            "INSERT INTO tokens (token, username, created_at, expires_at) VALUES (%s, %s, %s, %s)",
            (token, row["username"], security.utc_now(), expires.strftime("%Y-%m-%dT%H:%M:%SZ")),
        )
        conn.commit()
        return {"token": token, "username": row["username"]}
    finally:
        conn.close()


def logout_user(token: str) -> None:
    conn = connect_db()
    try:
        conn.execute("DELETE FROM tokens WHERE token = %s", (token,))
        conn.commit()
    finally:
        conn.close()


def get_username_by_token(token: str) -> str | None:
    """校验 token 存在且未过期，返回用户名；无效返回 None。"""
    user = get_user_by_token(token)
    return user["username"] if user else None


def get_user_by_token(token: str) -> dict | None:
    """校验 token 存在且未过期，返回 {username, user_id}；无效返回 None。"""
    conn = connect_db()
    try:
        row = conn.execute(
            "SELECT t.username, u.id AS user_id FROM tokens t JOIN users u ON u.username = t.username "
            "WHERE t.token = %s AND t.expires_at > %s",
            (token, security.utc_now()),
        ).fetchone()
        return {"username": row["username"], "user_id": row["user_id"]} if row else None
    finally:
        conn.close()
