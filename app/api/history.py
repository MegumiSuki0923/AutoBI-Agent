from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

from app.services.history_service import HistoryService

router = APIRouter()

class SessionResponse(BaseModel):
    session_id: str
    title: str
    created_at: str | None
    updated_at: str | None

class MessageResponse(BaseModel):
    role: str
    content: str
    created_at: str | None

def get_history_service() -> HistoryService:
    return HistoryService()

@router.get("/sessions", response_model=List[SessionResponse], summary="拉取所有会话列表")
def list_sessions(limit: int = 50, history_service: HistoryService = Depends(get_history_service)):
    try:
        return history_service.get_sessions(limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse], summary="拉取某个会话的聊天记录")
def list_messages(session_id: str, history_service: HistoryService = Depends(get_history_service)):
    try:
        return history_service.get_messages(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/sessions/{session_id}", summary="删除某个会话及其聊天记录")
def delete_session(session_id: str, history_service: HistoryService = Depends(get_history_service)):
    try:
        history_service.delete_session(session_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SessionRenameRequest(BaseModel):
    title: str

@router.put("/sessions/{session_id}", summary="重命名某个会话")
def rename_session(session_id: str, req: SessionRenameRequest, history_service: HistoryService = Depends(get_history_service)):
    try:
        history_service.update_session_title(session_id, req.title)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
