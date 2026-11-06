"""对话流式接口（SSE，需求文档 7.2 节；FR-21 会话按用户隔离）。"""
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user
from app.schemas.api import ChatRequest
from app.services import session_service
from app.services.chat_service import chat_event_stream

router = APIRouter(prefix="/api", tags=["chat"])

UNTITLED = "新会话"


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: str, body: ChatRequest, user: dict = Depends(get_current_user)):
    session = session_service.get_session(user["user_id"], session_id)
    if not session:
        # 不存在或不属于当前用户，统一 404（不泄露存在性）
        raise HTTPException(status_code=404, detail="会话不存在")

    # FR-8：新会话标题取首条提问前 20 字
    if session["title"] == UNTITLED:
        session_service.rename_session(user["user_id"], session_id, body.message.strip()[:20])

    return EventSourceResponse(chat_event_stream(user["user_id"], session_id, body.message.strip()))


@router.post("/chat")
async def chat_auto_create(body: ChatRequest, user: dict = Depends(get_current_user)):
    """无会话 ID 时自动创建会话（协议约定）。"""
    session = session_service.create_session(user["user_id"], body.message.strip()[:20])
    return EventSourceResponse(chat_event_stream(user["user_id"], session["id"], body.message.strip()))
