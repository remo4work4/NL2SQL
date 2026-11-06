"""会话管理接口（FR-8/9/12；FR-21 按用户隔离）。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.schemas.api import SessionCreate, SessionDetail, SessionOut, SessionRename
from app.services import session_service

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=SessionOut)
def create_session(body: SessionCreate, user: dict = Depends(get_current_user)):
    return session_service.create_session(user["user_id"], body.title)


@router.get("", response_model=list[SessionOut])
def list_sessions(user: dict = Depends(get_current_user)):
    return session_service.list_sessions(user["user_id"])


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, user: dict = Depends(get_current_user)):
    session = session_service.get_session(user["user_id"], session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    session["messages"] = session_service.get_messages(user["user_id"], session_id)
    return session


@router.patch("/{session_id}", response_model=SessionOut)
def rename_session(session_id: str, body: SessionRename, user: dict = Depends(get_current_user)):
    if not session_service.rename_session(user["user_id"], session_id, body.title):
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_service.get_session(user["user_id"], session_id)


@router.delete("/{session_id}")
def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    if not session_service.delete_session(user["user_id"], session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}
