from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status

from app.schemas import AskRequest, AskResponse, QueryResult
from app.services.analysis_service import AnalysisService
from app.services.chart_service import ChartService
from app.services.history_service import HistoryService
from app.services.rag_service import RAGService
from app.services.sql_executor import SQLExecutor
from app.services.sql_guard import SQLGuard
from app.services.text_to_sql_service import TextToSQLService


router = APIRouter()


class AskPipeline:
    """编排真实问数链路：RAG -> Text-to-SQL -> SQL Guard -> DuckDB -> 分析与日志。"""

    def __init__(
        self,
        *,
        rag_service: Optional[RAGService] = None,
        text_to_sql_service: Optional[TextToSQLService] = None,
        sql_guard: Optional[SQLGuard] = None,
        sql_executor: Optional[SQLExecutor] = None,
        chart_service: Optional[ChartService] = None,
        analysis_service: Optional[AnalysisService] = None,
        history_service: Optional[HistoryService] = None,
    ):
        self.rag_service = rag_service or RAGService()
        self.text_to_sql_service = text_to_sql_service or TextToSQLService()
        self.sql_guard = sql_guard or SQLGuard()
        self.sql_executor = sql_executor or SQLExecutor()
        self.chart_service = chart_service or ChartService()
        self.analysis_service = analysis_service or AnalysisService()
        self.history_service = history_service or HistoryService()

    def run(self, question: str) -> AskResponse:
        start_time = time.time()
        raw_sql: Optional[str] = None
        safe_sql: Optional[str] = None

        try:
            schema_context, metric_context = self._retrieve_context(question)
            raw_sql, _reason = self.text_to_sql_service.generate_sql(
                question=question,
                schema_context=schema_context,
                metric_context=metric_context,
            )
            safe_sql = self.sql_guard.validate_and_rewrite(raw_sql)

            columns, rows = self.sql_executor.execute(safe_sql)
            chart_suggestion = self.chart_service.recommend_chart(
                question=question,
                columns=columns,
                rows=rows,
            )
            analysis = self.analysis_service.generate_analysis(
                question=question,
                sql=safe_sql,
                columns=columns,
                rows=rows,
            )

            execution_time_ms = self._elapsed_ms(start_time)
            self.history_service.record_success(
                question=question,
                sql=safe_sql,
                row_count=len(rows),
                chart_type=chart_suggestion.chart_type,
                execution_time_ms=execution_time_ms,
                analysis=analysis,
            )

            return AskResponse(
                query=question,
                sql=safe_sql,
                result=QueryResult(columns=columns, rows=rows),
                analysis=analysis,
                chart_suggestion=chart_suggestion,
                success=True,
                error_message=None,
                execution_time_ms=execution_time_ms,
            )

        except Exception as exc:
            execution_time_ms = self._elapsed_ms(start_time)
            error_message = str(exc)
            self.history_service.record_failure(
                question=question,
                error_message=error_message,
                sql=raw_sql or safe_sql,
                execution_time_ms=execution_time_ms,
            )

            return AskResponse(
                query=question,
                sql=safe_sql,
                result=None,
                analysis=None,
                chart_suggestion=None,
                success=False,
                error_message=error_message,
                execution_time_ms=execution_time_ms,
            )

    def _retrieve_context(self, question: str) -> tuple[str, str]:
        chunks = self.rag_service.retrieve(question, limit=6)
        return (
            self._format_context(chunks, source="data_dictionary.md"),
            self._format_context(chunks, source="metrics.md"),
        )

    def _format_context(self, chunks: List[Dict[str, Any]], source: str) -> str:
        matched_chunks = [chunk for chunk in chunks if chunk.get("source") == source]
        return "\n\n".join(
            f"### {chunk.get('title', '').strip()}\n{chunk.get('content', '').strip()}"
            for chunk in matched_chunks
            if chunk.get("content")
        )

    def _elapsed_ms(self, start_time: float) -> float:
        return round((time.time() - start_time) * 1000.0, 2)


def get_ask_pipeline() -> AskPipeline:
    return AskPipeline()


@router.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
    summary="智能数据查询接口",
    description=(
        "输入自然语言业务问题，系统经过 RAG 检索、Text-to-SQL、SQL 安全校验、"
        "DuckDB 查询、图表推荐、结果分析和历史记录后返回结构化问数结果。"
    ),
)
async def ask_question(
    payload: AskRequest,
    pipeline: AskPipeline = Depends(get_ask_pipeline),
) -> AskResponse:
    return pipeline.run(payload.query)
