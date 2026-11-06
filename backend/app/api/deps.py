"""FastAPI 依赖：登录态校验（FR-15/21）。

- get_current_username：返回用户名（无用户隔离要求的接口用）
- get_current_user：返回 {username, user_id}（会话/对话接口，按用户隔离）
"""
from fastapi import Header, HTTPException

from app.services.auth_service import get_user_by_token


def _parse_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或缺少凭证")
    return authorization[len("Bearer ") :].strip()


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    token = _parse_token(authorization)
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return user


def get_current_username(authorization: str | None = Header(default=None)) -> str:
    return get_current_user(authorization)["username"]
