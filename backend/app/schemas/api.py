"""API 请求/响应模型（需求文档第 7 章）。"""
from pydantic import BaseModel, Field


# ---- 认证（FR-15） ----
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    """注册（FR-21）。"""
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)


class LoginResponse(BaseModel):
    token: str
    username: str


class MeResponse(BaseModel):
    username: str


# ---- 会话（FR-8/9/12） ----
class SessionCreate(BaseModel):
    title: str = "新会话"


class SessionRename(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    sql: str | None = None
    chart_spec: dict | None = None
    result: dict | None = None
    status: str = "done"
    error: str | None = None
    created_at: str


class SessionDetail(SessionOut):
    messages: list[MessageOut]


# ---- 对话（SSE） ----
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


# ---- 表结构浏览（FR-13） ----
class TableColumn(BaseModel):
    name: str
    type: str


class TableInfo(BaseModel):
    table: str
    columns: list[TableColumn]
    row_count: int
