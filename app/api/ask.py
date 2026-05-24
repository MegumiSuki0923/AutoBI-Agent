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
        self._rag_service = rag_service
        self._text_to_sql_service = text_to_sql_service
        self._sql_guard = sql_guard
        self._sql_executor = sql_executor
        self._chart_service = chart_service
        self._analysis_service = analysis_service
        self._history_service = history_service

    @property
    def rag_service(self) -> RAGService:
        if self._rag_service is None:
            self._rag_service = RAGService()
        return self._rag_service

    @property
    def text_to_sql_service(self) -> TextToSQLService:
        if self._text_to_sql_service is None:
            self._text_to_sql_service = TextToSQLService()
        return self._text_to_sql_service

    @property
    def sql_guard(self) -> SQLGuard:
        if self._sql_guard is None:
            self._sql_guard = SQLGuard()
        return self._sql_guard

    @property
    def sql_executor(self) -> SQLExecutor:
        if self._sql_executor is None:
            self._sql_executor = SQLExecutor()
        return self._sql_executor

    @property
    def chart_service(self) -> ChartService:
        if self._chart_service is None:
            self._chart_service = ChartService()
        return self._chart_service

    @property
    def analysis_service(self) -> AnalysisService:
        if self._analysis_service is None:
            self._analysis_service = AnalysisService()
        return self._analysis_service

    @property
    def history_service(self) -> HistoryService:
        if self._history_service is None:
            self._history_service = HistoryService()
        return self._history_service

    def run(self, question: str) -> AskResponse:
        start_time = time.time()
        raw_sql: Optional[str] = None
        safe_sql: Optional[str] = None

        try:
            if not self._is_data_query(question):
                return self._build_daily_qa_response(question, start_time)

            schema_context, metric_context = self._retrieve_context(question)
            is_data_query, raw_sql, _reason, chat_reply = self.text_to_sql_service.generate_sql(
                question=question,
                schema_context=schema_context,
                metric_context=metric_context,
            )

            if not is_data_query:
                execution_time_ms = self._elapsed_ms(start_time)
                self.history_service.record_success(
                    question=question,
                    sql=None,
                    row_count=0,
                    chart_type=None,
                    execution_time_ms=execution_time_ms,
                    analysis=chat_reply,
                )
                return AskResponse(
                    query=question,
                    sql=None,
                    result=None,
                    analysis=chat_reply,
                    chart_suggestion=None,
                    success=True,
                    error_message=None,
                    execution_time_ms=execution_time_ms,
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

    def _is_data_query(self, question: str) -> bool:
        normalized = question.strip().lower()
        if not normalized:
            return False

        daily_keywords = {
            "你好",
            "您好",
            "你是谁",
            "介绍一下",
            "谢谢",
            "感谢",
            "可以查询什么",
            "能查询什么",
            "能问什么",
            "可以问什么",
            "有什么数据",
            "有哪些数据",
            "支持什么问题",
            "支持哪些问题",
            "查询范围",
            "帮助",
            "help",
            "你能做什么",
            "你可以做什么",
            "怎么用",
            "使用方法",
        }

        # 快速判断路径：如果是极其简单且明确的日常对话/说明性质指令，走快速响应逻辑（节省调用大模型成本）
        if any(keyword in normalized for keyword in daily_keywords):
            return False

        # 其余更复杂的询问（可能包含模糊的数据诉求）默认交付大模型在 Text-to-SQL 环节做智能意图判定
        return True

    def _build_daily_qa_response(self, question: str, start_time: float) -> AskResponse:
        analysis = self._build_daily_qa_analysis(question)
        rows = self._supported_question_rows()
        execution_time_ms = self._elapsed_ms(start_time)
        self.history_service.record_success(
            question=question,
            sql=None,
            row_count=len(rows),
            chart_type=None,
            execution_time_ms=execution_time_ms,
            analysis=analysis,
        )
        return AskResponse(
            query=question,
            sql=None,
            result=QueryResult(
                columns=["table_name", "business_scope"],
                rows=rows,
            ),
            analysis=analysis,
            chart_suggestion=None,
            success=True,
            error_message=None,
            execution_time_ms=execution_time_ms,
        )

    def _supported_question_rows(self) -> List[List[str]]:
        rows = [
            [
                "fact_vehicle_prod_sales_monthly",
                "汽车品牌车型月度产销表：车型销量、品牌产销、总汽车销量",
            ],
            [
                "fact_nev_manufacturer_monthly",
                "新能源厂商月度产销表：厂商销量排名、厂商销量趋势、产销对比",
            ],
            [
                "fact_nev_overall_monthly",
                "新能源总体月度产销表：新能源总量、燃料类型结构、渗透率趋势",
            ],
            [
                "fact_charging_infrastructure_monthly",
                "充电设施月度指标表：省份充电设施数量、区域分布、增长变化",
            ],
            [
                "fact_battery_installation_monthly",
                "动力电池月度装车指标表：材料类型、车型类别、装车量结构",
            ],
        ]
        return rows

    def _build_daily_qa_analysis(self, question: str) -> str:
        normalized = question.strip().lower()

        if any(keyword in normalized for keyword in {"你好", "您好"}):
            return (
                "你好，我是 AutoBI Agent，主要帮助你查询汽车产业数据。"
                "你可以问厂商销量、车型销量、新能源渗透率、充电设施和动力电池装车量等问题。"
            )

        if any(keyword in normalized for keyword in {"你是谁", "介绍一下", "你能做什么", "你可以做什么"}):
            return (
                "我是 AutoBI Agent，一个面向汽车产业数据的问数助手。"
                "我会把数据类问题转换为安全 SQL，查询 DuckDB，并返回表格、图表建议和分析结论。"
            )

        if any(keyword in normalized for keyword in {"谢谢", "感谢"}):
            return "不客气。你可以继续输入汽车产业相关问题，我会优先返回 SQL、查询结果和分析结论。"

        if any(
            keyword in normalized
            for keyword in {
                "可以查询什么",
                "能查询什么",
                "能问什么",
                "可以问什么",
                "有什么数据",
                "有哪些数据",
                "支持什么问题",
                "支持哪些问题",
                "查询范围",
                "帮助",
                "help",
                "怎么用",
                "使用方法",
            }
        ):
            return (
                "目前可以查询 5 张业务表：汽车品牌车型月度产销表、新能源厂商月度产销表、"
                "新能源总体月度产销表、充电设施月度指标表和动力电池月度装车指标表。"
                "你可以直接点击业务查询范围，也可以按时间、厂商、车型、省份或材料类型继续追问。"
            )

        return (
            "当前我主要支持汽车产业数据问数，不处理天气、写作或通用闲聊类任务。"
            "你可以改问厂商销量、车型销量、新能源渗透率、充电设施或动力电池装车量相关问题。"
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
