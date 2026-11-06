"""认证接口（FR-15/21）：注册 / 登录 / 登出 / 当前用户。"""
from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import get_current_username
from app.schemas.api import LoginRequest, LoginResponse, MeResponse, RegisterRequest
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=LoginResponse)
def register(body: RegisterRequest):
    """注册新用户（FR-21）：用户名唯一，成功后直接登录。"""
    try:
        return auth_service.register_user(body.username, body.password)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=409 if "已存在" in str(e) else 400, detail=str(e)) from e


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest):
    try:
        return auth_service.login_user(body.username, body.password)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.post("/logout")
def logout(
    authorization: str | None = Header(default=None),
    _: str = Depends(get_current_username),
):
    if authorization and authorization.startswith("Bearer "):
        auth_service.logout_user(authorization[len("Bearer ") :].strip())
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
def me(username: str = Depends(get_current_username)):
    return {"username": username}
