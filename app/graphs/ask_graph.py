from __future__ import annotations

import json
import time
from operator import add
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.schemas import AskResponse, ChartSuggestion, QueryResult
from app.services.analysis_service import AnalysisService
from app.services.chart_service import ChartService
from app.services.history_service import HistoryService
from app.services.rag_service import RAGService
from app.services.sql_executor import SQLExecutor
from app.services.sql_guard import SQLGuard
from app.services.text_to_sql_service import TextToSQLService
from app.services.table_routing_service import TableRoutingService


class AskGraphState(TypedDict, total=False):
    question: str
    start_time: float
    is_data_query: bool
    selected_tables: List[str]
    raw_sql: Optional[str]
    safe_sql: Optional[str]
    schema_context: str
    metric_context: str
    chat_reply: Optional[str]
    columns: List[str]
    rows: List[List[Any]]
    chart_suggestion: Optional[ChartSuggestion]
    analysis: Optional[str]
    error_message: Optional[str]
    response: AskResponse
    execution_steps: Annotated[List[Dict[str, Any]], add]
    history: Annotated[List[Dict[str, str]], add]
    context_history: List[Dict[str, str]]
    repair_attempts: int
    last_failed_step: Optional[str]
    failed_sql: Optional[str]
    repair_error: Optional[str]


class AskGraph:
    """LangGraph 编排的问数链路。"""

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
        table_routing_service: Optional[TableRoutingService] = None,
        max_repair_attempts: int = 2,
    ):
        self._rag_service = rag_service
        self._text_to_sql_service = text_to_sql_service
        self._sql_guard = sql_guard
        self._sql_executor = sql_executor
        self._chart_service = chart_service
        self._analysis_service = analysis_service
        self._history_service = history_service
        self._table_routing_service = table_routing_service
        self.max_repair_attempts = max_repair_attempts
        self.memory = MemorySaver()
        self._graph = self._build_graph()

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

    @property
    def table_routing_service(self) -> TableRoutingService:
        if self._table_routing_service is None:
            self._table_routing_service = TableRoutingService()
        return self._table_routing_service

    def run(self, question: str, thread_id: Optional[str] = None) -> AskResponse:
        import uuid
        thread_id = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        state = self._graph.invoke(
            self._initial_state(question, thread_id),
            config=config,
        )
        return state["response"]

    async def astream(self, question: str, thread_id: Optional[str] = None):
        import json
        import uuid
        from fastapi.encoders import jsonable_encoder

        thread_id = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        events = self._graph.stream(
            self._initial_state(question, thread_id),
            stream_mode="debug",
            config=config,
        )
        for event in events:
            event_type = event.get("type")
            payload = event.get("payload", {})
            node_name = payload.get("name")

            if event_type == "task" and node_name:
                step = self._step(
                    name=node_name,
                    status="running",
                    message=self._running_step_message(node_name),
                    elapsed_ms=0,
                )
                yield f"data: {json.dumps({'type': 'step_start', 'data': jsonable_encoder(step)}, ensure_ascii=False)}\n\n"

            if event_type != "task_result":
                continue

            result = payload.get("result") or {}
            if "execution_steps" in result and result["execution_steps"]:
                step = result["execution_steps"][-1]
                yield f"data: {json.dumps({'type': 'step', 'data': jsonable_encoder(step)}, ensure_ascii=False)}\n\n"

            if node_name == "build_response" and "response" in result:
                response_dict = jsonable_encoder(result["response"])
                yield f"data: {json.dumps({'type': 'result', 'data': response_dict}, ensure_ascii=False)}\n\n"


    def _build_graph(self):
        builder = StateGraph(AskGraphState)
        builder.add_node("intent_check", self._intent_check)
        builder.add_node("daily_qa", self._daily_qa)
        builder.add_node("route_table", self._route_table)
        builder.add_node("retrieve_context", self._retrieve_context)
        builder.add_node("generate_sql", self._generate_sql)
        builder.add_node("guard_sql", self._guard_sql)
        builder.add_node("repair_sql", self._repair_sql)
        builder.add_node("execute_sql", self._execute_sql)
        builder.add_node("recommend_chart", self._recommend_chart)
        builder.add_node("generate_analysis", self._generate_analysis)
        builder.add_node("record_success", self._record_success)
        builder.add_node("record_failure", self._record_failure)
        builder.add_node("build_response", self._build_response)

        builder.add_edge(START, "intent_check")
        builder.add_conditional_edges(
            "intent_check",
            self._route_after_intent,
            {
                "daily_qa": "daily_qa",
                "route_table": "route_table",
            },
        )
        builder.add_edge("daily_qa", "record_success")
        builder.add_conditional_edges(
            "route_table",
            self._route_error_or_next("retrieve_context"),
            {
                "record_failure": "record_failure",
                "retrieve_context": "retrieve_context",
            },
        )
        builder.add_conditional_edges(
            "retrieve_context",
            self._route_error_or_next("generate_sql"),
            {
                "record_failure": "record_failure",
                "generate_sql": "generate_sql",
            },
        )
        builder.add_conditional_edges(
            "generate_sql",
            self._route_after_generate_sql,
            {
                "record_failure": "record_failure",
                "record_success": "record_success",
                "guard_sql": "guard_sql",
            },
        )
        builder.add_conditional_edges(
            "guard_sql",
            self._route_after_sql_step("execute_sql"),
            {
                "record_failure": "record_failure",
                "repair_sql": "repair_sql",
                "execute_sql": "execute_sql",
            },
        )
        builder.add_conditional_edges(
            "execute_sql",
            self._route_after_sql_step("recommend_chart"),
            {
                "record_failure": "record_failure",
                "repair_sql": "repair_sql",
                "recommend_chart": "recommend_chart",
            },
        )
        builder.add_conditional_edges(
            "repair_sql",
            self._route_after_repair_sql,
            {
                "record_failure": "record_failure",
                "guard_sql": "guard_sql",
            },
        )
        builder.add_conditional_edges(
            "recommend_chart",
            self._route_error_or_next("generate_analysis"),
            {
                "record_failure": "record_failure",
                "generate_analysis": "generate_analysis",
            },
        )
        builder.add_conditional_edges(
            "generate_analysis",
            self._route_error_or_next("record_success"),
            {
                "record_failure": "record_failure",
                "record_success": "record_success",
            },
        )
        builder.add_conditional_edges(
            "record_success",
            self._route_error_or_next("build_response"),
            {
                "record_failure": "record_failure",
                "build_response": "build_response",
            },
        )
        builder.add_edge("record_failure", "build_response")
        builder.add_edge("build_response", END)
        return builder.compile(checkpointer=self.memory)

    def _intent_check(self, state: AskGraphState) -> Dict[str, Any]:
        return self._run_step(
            "intent_check",
            lambda: {"is_data_query": self._is_data_query(state["question"])},
            lambda updates: "需要进入数据问数链路"
            if updates["is_data_query"]
            else "识别为日常/能力说明问题",
        )

    def _daily_qa(self, state: AskGraphState) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            return {
                "columns": ["table_name", "business_scope"],
                "rows": self._supported_question_rows(),
                "analysis": self._build_daily_qa_analysis(state["question"]),
            }

        return self._run_step("daily_qa", run, "已生成能力说明回复")

    def _route_table(self, state: AskGraphState) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            tables = self.table_routing_service.route_tables(
                question=state["question"],
                history=self._context_history(state)
            )
            return {"selected_tables": tables}

        return self._run_step(
            "route_table",
            run,
            lambda updates: f"已选中相关数据表: {', '.join(updates['selected_tables'])}" if updates.get("selected_tables") else "未匹配到相关表"
        )

    def _retrieve_context(self, state: AskGraphState) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            # 使用精准提取
            chunks = self.rag_service.retrieve_by_tables(state.get("selected_tables", []))
            return {
                "schema_context": self._format_context(
                    chunks,
                    source="data_dictionary.md",
                ),
                "metric_context": self._format_context(chunks, source="metrics.md"),
            }

        return self._run_step("retrieve_context", run, "已检索数据字典和指标口径")

    def _generate_sql(self, state: AskGraphState) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            is_data_query, raw_sql, _reason, chat_reply = self.text_to_sql_service.generate_sql(
                question=state["question"],
                schema_context=state.get("schema_context", ""),
                metric_context=state.get("metric_context", ""),
                history=self._context_history(state)
            )
            return {
                "is_data_query": is_data_query,
                "raw_sql": raw_sql,
                "chat_reply": chat_reply,
                "analysis": chat_reply if not is_data_query else None,
            }

        return self._run_step(
            "generate_sql",
            run,
            lambda updates: "已生成候选 SQL"
            if updates["is_data_query"]
            else "模型判断为非数据问题",
        )

    def _guard_sql(self, state: AskGraphState) -> Dict[str, Any]:
        started_at = time.time()
        try:
            safe_sql = self.sql_guard.validate_and_rewrite(state["raw_sql"])
        except Exception as exc:
            return {
                "error_message": str(exc),
                "last_failed_step": "guard_sql",
                "failed_sql": state.get("raw_sql"),
                "repair_error": str(exc),
                "execution_steps": [
                    self._step(
                        name="guard_sql",
                        status="failed",
                        message=str(exc),
                        elapsed_ms=self._elapsed_ms(started_at),
                    )
                ],
            }

        return {
            "safe_sql": safe_sql,
            "error_message": None,
            "last_failed_step": None,
            "failed_sql": None,
            "repair_error": None,
            "execution_steps": [
                self._step(
                    name="guard_sql",
                    status="success",
                    message="SQL 已通过安全校验",
                    elapsed_ms=self._elapsed_ms(started_at),
                )
            ],
        }

    def _execute_sql(self, state: AskGraphState) -> Dict[str, Any]:
        started_at = time.time()
        try:
            columns, rows = self.sql_executor.execute(state["safe_sql"])
        except Exception as exc:
            return {
                "error_message": str(exc),
                "last_failed_step": "execute_sql",
                "failed_sql": state.get("safe_sql"),
                "repair_error": str(exc),
                "execution_steps": [
                    self._step(
                        name="execute_sql",
                        status="failed",
                        message=str(exc),
                        elapsed_ms=self._elapsed_ms(started_at),
                    )
                ],
            }

        return {
            "columns": columns,
            "rows": rows,
            "error_message": None,
            "last_failed_step": None,
            "failed_sql": None,
            "repair_error": None,
            "execution_steps": [
                self._step(
                    name="execute_sql",
                    status="success",
                    message=f"查询完成，返回 {len(rows)} 行",
                    elapsed_ms=self._elapsed_ms(started_at),
                )
            ],
        }

    def _repair_sql(self, state: AskGraphState) -> Dict[str, Any]:
        started_at = time.time()
        attempt = int(state.get("repair_attempts") or 0) + 1
        failed_sql = state.get("failed_sql") or state.get("raw_sql") or state.get("safe_sql") or ""
        repair_error = state.get("repair_error") or state.get("error_message") or "SQL 执行失败"

        try:
            repaired_sql, _reason = self.text_to_sql_service.repair_sql(
                question=state["question"],
                failed_sql=failed_sql,
                error_message=repair_error,
                schema_context=state.get("schema_context", ""),
                metric_context=state.get("metric_context", ""),
                history=self._context_history(state),
            )
        except Exception as exc:
            return {
                "repair_attempts": attempt,
                "error_message": str(exc),
                "last_failed_step": "repair_sql",
                "failed_sql": failed_sql,
                "repair_error": str(exc),
                "execution_steps": [
                    self._step(
                        name="repair_sql",
                        status="failed",
                        message=str(exc),
                        elapsed_ms=self._elapsed_ms(started_at),
                    )
                ],
            }

        return {
            "raw_sql": repaired_sql,
            "safe_sql": None,
            "repair_attempts": attempt,
            "error_message": None,
            "last_failed_step": None,
            "failed_sql": None,
            "repair_error": None,
            "execution_steps": [
                self._step(
                    name="repair_sql",
                    status="success",
                    message=f"已完成第 {attempt} 次 SQL 自动修复",
                    elapsed_ms=self._elapsed_ms(started_at),
                )
            ],
        }

    def _recommend_chart(self, state: AskGraphState) -> Dict[str, Any]:
        return self._run_step(
            "recommend_chart",
            lambda: {
                "chart_suggestion": self.chart_service.recommend_chart(
                    question=state["question"],
                    columns=state.get("columns", []),
                    rows=state.get("rows", []),
                )
            },
            "已生成图表推荐",
        )

    def _generate_analysis(self, state: AskGraphState) -> Dict[str, Any]:
        return self._run_step(
            "generate_analysis",
            lambda: {
                "analysis": self.analysis_service.generate_analysis(
                    question=state["question"],
                    sql=state["safe_sql"],
                    columns=state.get("columns", []),
                    rows=state.get("rows", []),
                )
            },
            "已生成分析结论",
        )

    def _record_success(self, state: AskGraphState) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            chart_suggestion = state.get("chart_suggestion")
            rows = state.get("rows", [])
            self.history_service.record_success(
                question=state["question"],
                sql=state.get("safe_sql"),
                row_count=len(rows),
                chart_type=chart_suggestion.chart_type if chart_suggestion else None,
                execution_time_ms=self._elapsed_ms(state["start_time"]),
                analysis=state.get("analysis"),
            )
            return {}

        return self._run_step("record_success", run, "已写入成功历史记录")

    def _record_failure(self, state: AskGraphState) -> Dict[str, Any]:
        def run() -> Dict[str, Any]:
            self.history_service.record_failure(
                question=state["question"],
                error_message=state.get("error_message") or "问数链路执行失败",
                sql=state.get("failed_sql") or state.get("raw_sql") or state.get("safe_sql"),
                execution_time_ms=self._elapsed_ms(state["start_time"]),
            )
            return {}

        return self._run_step("record_failure", run, "已写入失败历史记录")

    def _build_response(self, state: AskGraphState, config: RunnableConfig) -> Dict[str, Any]:
        started_at = time.time()
        columns = state.get("columns")
        rows = state.get("rows")
        result = None
        if columns is not None and rows is not None:
            result = QueryResult(columns=columns, rows=rows)

        step = self._step(
            name="build_response",
            status="success",
            message="已生成 API 响应",
            elapsed_ms=self._elapsed_ms(started_at),
        )
        execution_steps = state.get("execution_steps", []) + [step]

        response = AskResponse(
            query=state["question"],
            sql=state.get("safe_sql"),
            result=None if state.get("error_message") else result,
            analysis=None if state.get("error_message") else state.get("analysis"),
            chart_suggestion=None
            if state.get("error_message")
            else state.get("chart_suggestion"),
            success=not bool(state.get("error_message")),
            error_message=state.get("error_message"),
            execution_time_ms=self._elapsed_ms(state["start_time"]),
            execution_steps=execution_steps,
        )
        assistant_reply = state.get("analysis") or state.get("chat_reply") or state.get("error_message") or "无返回内容"

        # Save to history
        try:
            thread_id = config.get("configurable", {}).get("thread_id")
            if thread_id:
                import json
                from fastapi.encoders import jsonable_encoder

                # 为保留完整的多模态响应（图表、SQL、表格），我们将整个 response 对象序列化保存
                assistant_content = json.dumps(jsonable_encoder(response), ensure_ascii=False)

                history_delta = [
                    {"role": "user", "content": state["question"]},
                    {"role": "assistant", "content": assistant_content}
                ]
                self.history_service.create_or_update_session(thread_id, state["question"][:20])
                self.history_service.add_chat_messages(thread_id, history_delta)
        except Exception as e:
            print(f"Error saving history: {e}")

        return {
            "response": response,
            "execution_steps": [step],
            "history": [
                {"role": "user", "content": state["question"]},
                {"role": "assistant", "content": str(assistant_reply)}
            ]
        }

    def _initial_state(self, question: str, thread_id: Optional[str]) -> Dict[str, Any]:
        state: Dict[str, Any] = {
            "question": question,
            "start_time": time.time(),
            "execution_steps": [],
            "repair_attempts": 0,
        }
        context_history = self._load_context_history(thread_id)
        if context_history:
            state["context_history"] = context_history
        return state

    def _context_history(self, state: AskGraphState) -> List[Dict[str, str]]:
        return state.get("context_history") or state.get("history") or []

    def _load_context_history(self, thread_id: Optional[str]) -> List[Dict[str, str]]:
        if not thread_id:
            return []

        try:
            get_messages = getattr(self.history_service, "get_messages", None)
            if get_messages is None:
                return []
            messages = get_messages(thread_id)
        except Exception as exc:
            print(f"Error loading context history: {exc}")
            return []

        return self._format_context_history(messages)

    def _format_context_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        formatted: List[Dict[str, str]] = []
        for message in messages[-8:]:
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if not content:
                continue

            if role == "assistant":
                content = self._summarize_assistant_content(content)
            elif role != "user":
                role = "user"

            if content:
                formatted.append({"role": role, "content": content[:4000]})

        return formatted

    def _summarize_assistant_content(self, content: str) -> str:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return content.strip()

        if not isinstance(payload, dict):
            return content.strip()

        parts: List[str] = []
        query = payload.get("query")
        if query:
            parts.append(f"上一轮问题: {query}")

        sql = payload.get("sql")
        if sql:
            parts.append(f"上一轮 SQL: {sql}")

        result = payload.get("result") or {}
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        if columns:
            parts.append("上一轮结果字段: " + ", ".join(str(column) for column in columns))
        if rows:
            row_summaries = [
                self._format_result_row(columns, row)
                for row in rows[:10]
            ]
            parts.append("上一轮结果前几行: " + "; ".join(row_summaries))

        analysis = payload.get("analysis")
        if analysis:
            parts.append(f"上一轮分析摘要: {analysis}")

        return "\n".join(parts) if parts else content.strip()

    def _format_result_row(self, columns: List[Any], row: Any) -> str:
        if isinstance(row, list) and columns:
            pairs = []
            for index, value in enumerate(row):
                column = columns[index] if index < len(columns) else f"col_{index + 1}"
                pairs.append(f"{column}={self._stringify_cell(value)}")
            return ", ".join(pairs)
        return self._stringify_cell(row)

    def _stringify_cell(self, value: Any) -> str:
        if value is None:
            return "NULL"
        return str(value)

    def _run_step(self, name: str, run, success_message) -> Dict[str, Any]:
        started_at = time.time()
        try:
            updates = run()
        except Exception as exc:
            return {
                "error_message": str(exc),
                "execution_steps": [
                    self._step(
                        name=name,
                        status="failed",
                        message=str(exc),
                        elapsed_ms=self._elapsed_ms(started_at),
                    )
                ],
            }

        message = success_message(updates) if callable(success_message) else success_message
        return {
            **updates,
            "execution_steps": [
                self._step(
                    name=name,
                    status="success",
                    message=message,
                    elapsed_ms=self._elapsed_ms(started_at),
                )
            ],
        }

    def _route_after_intent(self, state: AskGraphState) -> str:
        return "route_table" if state.get("is_data_query") else "daily_qa"

    def _route_after_generate_sql(self, state: AskGraphState) -> str:
        if state.get("error_message"):
            return "record_failure"
        return "guard_sql" if state.get("is_data_query") else "record_success"

    def _route_after_sql_step(self, next_node: str):
        def route(state: AskGraphState) -> str:
            if not state.get("error_message"):
                return next_node
            return "repair_sql" if self._can_repair_sql(state) else "record_failure"

        return route

    def _route_after_repair_sql(self, state: AskGraphState) -> str:
        if state.get("error_message"):
            return "record_failure"
        return "guard_sql"

    def _route_error_or_next(self, next_node: str):
        def route(state: AskGraphState) -> str:
            return "record_failure" if state.get("error_message") else next_node

        return route

    def _can_repair_sql(self, state: AskGraphState) -> bool:
        if not state.get("is_data_query"):
            return False
        if int(state.get("repair_attempts") or 0) >= self.max_repair_attempts:
            return False
        failed_sql = state.get("failed_sql") or state.get("raw_sql") or state.get("safe_sql")
        return bool(failed_sql)

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

        return not any(keyword in normalized for keyword in daily_keywords)

    def _supported_question_rows(self) -> List[List[str]]:
        return [
            [
                "ads_vehicle_model_sales_rank",
                "车型销量排名应用表：年度车型销量 Top N、厂商车型对比",
            ],
            [
                "ads_nev_manufacturer_sales_rank",
                "新能源厂商销量排名应用表：年度厂商销量排名、头部厂商对比",
            ],
            [
                "ads_nev_penetration_trend",
                "新能源渗透率趋势应用表：月度新能源销量和渗透率趋势",
            ],
            [
                "ads_charging_facility_province_distribution",
                "充电设施省份分布应用表：省份充电设施数量和区域分布",
            ],
            [
                "ads_battery_material_share",
                "动力电池材料结构应用表：材料类型装车量和占比",
            ],
        ]

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
                "我会把数据类问题转换为安全 SQL，查询 Doris 数仓，并返回表格、图表建议和分析结论。"
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
                "目前可以查询 ADS 应用层和 DWS 汇总层：厂商销量排名、车型销量排名、"
                "新能源渗透率趋势、充电设施省份分布和动力电池装车结构。"
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

    def _step(
        self,
        *,
        name: str,
        status: str,
        message: str,
        elapsed_ms: float,
    ) -> Dict[str, Any]:
        return {
            "name": name,
            "status": status,
            "message": message,
            "elapsed_ms": elapsed_ms,
        }

    def _running_step_message(self, name: str) -> str:
        messages = {
            "intent_check": "正在识别问题意图",
            "daily_qa": "正在生成能力说明回复",
            "route_table": "正在分析关联数据表",
            "retrieve_context": "正在提取表结构细节和指标口径",
            "generate_sql": "正在生成候选 SQL",
            "guard_sql": "正在进行 SQL 安全校验",
            "repair_sql": "正在自动修复 SQL",
            "execute_sql": "正在查询 Doris 数仓",
            "recommend_chart": "正在推荐可视化图表",
            "generate_analysis": "正在生成分析结论",
            "record_success": "正在保存成功历史记录",
            "record_failure": "正在保存失败历史记录",
            "build_response": "正在生成 API 响应",
        }
        return messages.get(name, f"正在执行 {name}")

    def _elapsed_ms(self, start_time: float) -> float:
        return round((time.time() - start_time) * 1000.0, 2)
