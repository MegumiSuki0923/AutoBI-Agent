from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse

from app.schemas import AskRequest, AskResponse
from app.services.ask_service import AskService


router = APIRouter()


def get_ask_service() -> AskService:
    return AskService()


@router.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
    summary="智能数据查询接口",
    description=(
        "输入自然语言业务问题，系统经过 LangGraph 编排 RAG 检索、Text-to-SQL、"
        "SQL 安全校验、Doris 数仓查询、图表推荐、结果分析和历史记录后返回结构化问数结果。"
    ),
)
async def ask_question(
    payload: AskRequest,
    ask_service: AskService = Depends(get_ask_service),
) -> AskResponse:
    import uuid
    thread_id = payload.thread_id or str(uuid.uuid4())
    return ask_service.run(payload.query, thread_id)

@router.post(
    "/ask/stream",
    status_code=status.HTTP_200_OK,
    summary="智能数据查询接口(流式 SSE)",
    description="返回 SSE 事件流，实时下发执行步骤和最终结果。",
)
async def ask_question_stream(
    payload: AskRequest,
    ask_service: AskService = Depends(get_ask_service),
) -> StreamingResponse:
    import uuid
    thread_id = payload.thread_id or str(uuid.uuid4())
    return StreamingResponse(
        ask_service.astream(payload.query, thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
