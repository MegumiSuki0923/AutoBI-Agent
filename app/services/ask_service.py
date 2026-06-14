from __future__ import annotations

from typing import Optional

from app.graphs.ask_graph import AskGraph
from app.schemas import AskResponse
from app.services.analysis_service import AnalysisService
from app.services.chart_service import ChartService
from app.services.history_service import HistoryService
from app.services.rag_service import RAGService
from app.services.sql_executor import SQLExecutor
from app.services.sql_guard import SQLGuard
from app.services.table_routing_service import TableRoutingService
from app.services.text_to_sql_service import TextToSQLService


class AskService:
    """HTTP 入口之下的应用服务，实际编排交给 LangGraph。"""

    def __init__(
        self,
        *,
        ask_graph: Optional[AskGraph] = None,
        rag_service: Optional[RAGService] = None,
        text_to_sql_service: Optional[TextToSQLService] = None,
        sql_guard: Optional[SQLGuard] = None,
        sql_executor: Optional[SQLExecutor] = None,
        chart_service: Optional[ChartService] = None,
        analysis_service: Optional[AnalysisService] = None,
        history_service: Optional[HistoryService] = None,
        table_routing_service: Optional[TableRoutingService] = None,
        max_repair_attempts: int = 2,
    ):
        self.ask_graph = ask_graph or AskGraph(
            rag_service=rag_service,
            text_to_sql_service=text_to_sql_service,
            sql_guard=sql_guard,
            sql_executor=sql_executor,
            chart_service=chart_service,
            analysis_service=analysis_service,
            history_service=history_service,
            table_routing_service=table_routing_service,
            max_repair_attempts=max_repair_attempts,
        )

    @property
    def rag_service(self) -> RAGService:
        return self.ask_graph.rag_service

    @property
    def text_to_sql_service(self) -> TextToSQLService:
        return self.ask_graph.text_to_sql_service

    @property
    def sql_guard(self) -> SQLGuard:
        return self.ask_graph.sql_guard

    @property
    def sql_executor(self) -> SQLExecutor:
        return self.ask_graph.sql_executor

    @property
    def chart_service(self) -> ChartService:
        return self.ask_graph.chart_service

    @property
    def analysis_service(self) -> AnalysisService:
        return self.ask_graph.analysis_service

    @property
    def history_service(self) -> HistoryService:
        return self.ask_graph.history_service

    @property
    def table_routing_service(self) -> TableRoutingService:
        return self.ask_graph.table_routing_service

    def run(self, question: str, thread_id: Optional[str] = None) -> AskResponse:
        return self.ask_graph.run(question, thread_id)

    async def astream(self, question: str, thread_id: Optional[str] = None):
        async for chunk in self.ask_graph.astream(question, thread_id):
            yield chunk
