import asyncio
import json

import httpx

from app.api.ask import get_ask_service
from app.main import app
from app.schemas import ChartSuggestion
from app.services.ask_service import AskService
from app.services.sql_guard import SQLGuard


class ASGITestClient:
    def post(self, path, json=None):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.post(path, json=json)

        return asyncio.run(request())


class FakeRAGService:
    def __init__(self):
        self.queries = []
        self.table_queries = []

    def retrieve(self, query, limit=3):
        self.queries.append((query, limit))
        return [
            {
                "source": "data_dictionary.md",
                "title": "ads_nev_manufacturer_sales_rank",
                "content": "字段: stat_year, manufacturer_name, total_sales_units, sales_rank",
            },
            {
                "source": "metrics.md",
                "title": "厂商销量排名",
                "content": "优先查询 ads_nev_manufacturer_sales_rank 的 total_sales_units 和 sales_rank",
            },
        ]

    def retrieve_by_tables(self, table_names):
        self.table_queries.append(table_names)
        return [
            {
                "source": "data_dictionary.md",
                "title": "ads_nev_manufacturer_sales_rank",
                "content": "字段: stat_year, manufacturer_name, total_sales_units, sales_rank",
            },
            {
                "source": "metrics.md",
                "title": "厂商销量排名",
                "content": "优先查询 ads_nev_manufacturer_sales_rank 的 total_sales_units 和 sales_rank",
            },
        ]


class FakeTextToSQLService:
    def __init__(self, sql, repaired_sqls=None):
        self.sql = sql
        self.repaired_sqls = list(repaired_sqls or [])
        self.calls = []
        self.repair_calls = []

    def generate_sql(self, question, schema_context, metric_context, history=None):
        self.calls.append((question, schema_context, metric_context, history))
        if "天气" in question or "闲聊" in question:
            return False, None, "超出了数据库表范围。", "很抱歉，我目前仅支持汽车产业相关数据的智能问数，无法回答天气或闲聊类问题。"
        return True, self.sql, "按数据结构查询。", None

    def repair_sql(
        self,
        *,
        question,
        failed_sql,
        error_message,
        schema_context,
        metric_context,
        history=None,
    ):
        self.repair_calls.append(
            {
                "question": question,
                "failed_sql": failed_sql,
                "error_message": error_message,
                "schema_context": schema_context,
                "metric_context": metric_context,
                "history": history,
            }
        )
        if self.repaired_sqls:
            return self.repaired_sqls.pop(0), "已修复 SQL"
        return self.sql, "未提供修复 SQL，返回原 SQL"


class FakeTableRoutingService:
    def __init__(self, tables=None):
        self.tables = tables or ["ads_nev_manufacturer_sales_rank"]
        self.calls = []

    def route_tables(self, question, history=None):
        self.calls.append((question, history))
        return self.tables


class FakeSQLExecutor:
    def __init__(self, failures=None):
        self.executed_sql = None
        self.executed_sqls = []
        self.failures = list(failures or [])

    def execute(self, sql):
        self.executed_sql = sql
        self.executed_sqls.append(sql)
        if self.failures:
            failure = self.failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            raise RuntimeError(str(failure))
        return ["manufacturer_name", "total_sales"], [["比亚迪", 1860000]]


class FakeChartService:
    def __init__(self):
        self.calls = []

    def recommend_chart(self, question, columns, rows):
        self.calls.append((question, columns, rows))
        return ChartSuggestion(
            chart_type="bar",
            x_axis="manufacturer_name",
            y_axes=["total_sales"],
            title="厂商销量排名",
        )


class FakeAnalysisService:
    def __init__(self):
        self.calls = []

    def generate_analysis(self, question, sql, columns, rows):
        self.calls.append((question, sql, columns, rows))
        return "核心结论：比亚迪销量最高。"


class FakeHistoryService:
    def __init__(self, messages_by_session=None):
        self.success_records = []
        self.failure_records = []
        self.messages_by_session = messages_by_session or {}
        self.session_updates = []
        self.added_messages = []
        self.requested_sessions = []

    def record_success(self, **kwargs):
        self.success_records.append(kwargs)
        return 1

    def record_failure(self, **kwargs):
        self.failure_records.append(kwargs)
        return 1

    def get_messages(self, session_id):
        self.requested_sessions.append(session_id)
        return list(self.messages_by_session.get(session_id, []))

    def create_or_update_session(self, session_id, title):
        self.session_updates.append((session_id, title))

    def add_chat_messages(self, session_id, messages):
        self.added_messages.append((session_id, messages))
        self.messages_by_session.setdefault(session_id, []).extend(messages)


def _build_service(
    sql,
    *,
    history_messages=None,
    tables=None,
    repaired_sqls=None,
    executor_failures=None,
    max_repair_attempts=2,
):
    rag_service = FakeRAGService()
    text_to_sql_service = FakeTextToSQLService(sql, repaired_sqls=repaired_sqls)
    table_routing_service = FakeTableRoutingService(tables)
    sql_executor = FakeSQLExecutor(executor_failures)
    chart_service = FakeChartService()
    analysis_service = FakeAnalysisService()
    history_service = FakeHistoryService(history_messages)
    ask_service = AskService(
        rag_service=rag_service,
        text_to_sql_service=text_to_sql_service,
        table_routing_service=table_routing_service,
        sql_guard=SQLGuard(default_limit=100),
        sql_executor=sql_executor,
        chart_service=chart_service,
        analysis_service=analysis_service,
        history_service=history_service,
        max_repair_attempts=max_repair_attempts,
    )
    return ask_service


def _override_service(ask_service):
    async def override():
        return ask_service

    return override


def test_ask_api_runs_langgraph_service_with_safe_sql():
    ask_service = _build_service(
        """
        SELECT manufacturer_name, total_sales_units AS total_sales
        FROM ads_nev_manufacturer_sales_rank
        WHERE stat_year = 2022
        ORDER BY sales_rank
        """
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post(
            "/api/ask",
            json={"query": "2022 年各厂商新能源汽车销量排名如何？"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["query"] == "2022 年各厂商新能源汽车销量排名如何？"
    assert payload["sql"].endswith("LIMIT 100")
    assert payload["result"] == {
        "columns": ["manufacturer_name", "total_sales"],
        "rows": [["比亚迪", 1860000]],
    }
    assert payload["chart_suggestion"]["chart_type"] == "bar"
    assert payload["analysis"] == "核心结论：比亚迪销量最高。"
    assert [step["name"] for step in payload["execution_steps"]] == [
        "intent_check",
        "route_table",
        "retrieve_context",
        "generate_sql",
        "guard_sql",
        "execute_sql",
        "recommend_chart",
        "generate_analysis",
        "record_success",
        "build_response",
    ]
    assert {step["status"] for step in payload["execution_steps"]} == {"success"}

    assert ask_service.table_routing_service.calls[0][0] == "2022 年各厂商新能源汽车销量排名如何？"
    assert ask_service.rag_service.table_queries == [["ads_nev_manufacturer_sales_rank"]]
    assert "ads_nev_manufacturer_sales_rank" in ask_service.text_to_sql_service.calls[0][1]
    assert "total_sales_units" in ask_service.text_to_sql_service.calls[0][2]
    assert ask_service.sql_executor.executed_sql == payload["sql"]
    assert ask_service.history_service.success_records[0]["question"] == payload["query"]
    assert ask_service.history_service.success_records[0]["sql"] == payload["sql"]
    assert ask_service.history_service.success_records[0]["row_count"] == 1
    assert ask_service.history_service.success_records[0]["chart_type"] == "bar"


def test_ask_api_injects_session_history_for_followup_filters():
    thread_id = "session-followup"
    previous_response = {
        "query": "2022年销量前三的新能源厂商是谁？",
        "sql": (
            "SELECT manufacturer_name, total_sales_units "
            "FROM ads_nev_manufacturer_sales_rank "
            "WHERE stat_year = 2022 ORDER BY sales_rank LIMIT 3"
        ),
        "result": {
            "columns": ["manufacturer_name", "total_sales_units"],
            "rows": [
                ["比亚迪", 1860000],
                ["特斯拉", 710000],
                ["上汽", 530000],
            ],
        },
        "analysis": "2022 年销量前三的新能源厂商是比亚迪、特斯拉和上汽。",
        "success": True,
        "error_message": None,
        "execution_time_ms": 100,
        "execution_steps": [],
    }
    history_messages = {
        thread_id: [
            {
                "role": "user",
                "content": "2022年销量前三的新能源厂商是谁？",
                "created_at": "2026-06-14T10:00:00",
            },
            {
                "role": "assistant",
                "content": json.dumps(previous_response, ensure_ascii=False),
                "created_at": "2026-06-14T10:00:01",
            },
        ]
    }
    ask_service = _build_service(
        """
        SELECT manufacturer_name, SUM(phev_sales_units) AS phev_sales_units
        FROM dws_nev_manufacturer_sales_monthly
        WHERE manufacturer_name IN ('比亚迪', '特斯拉', '上汽')
        GROUP BY manufacturer_name
        ORDER BY phev_sales_units DESC
        """,
        history_messages=history_messages,
        tables=["dws_nev_manufacturer_sales_monthly"],
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post(
            "/api/ask",
            json={"query": "他们这三家的插混销量对比呢？", "thread_id": thread_id},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "manufacturer_name IN" in payload["sql"]

    routing_history = ask_service.table_routing_service.calls[0][1]
    sql_history = ask_service.text_to_sql_service.calls[0][3]
    history_text = "\n".join(message["content"] for message in sql_history)
    assert ask_service.history_service.requested_sessions == [thread_id]
    assert routing_history == sql_history
    assert "上一轮问题: 2022年销量前三的新能源厂商是谁？" in history_text
    assert "manufacturer_name=比亚迪" in history_text
    assert "manufacturer_name=特斯拉" in history_text
    assert "manufacturer_name=上汽" in history_text


def test_ask_api_repairs_sql_when_guard_rejects_first_candidate():
    bad_sql = "SELECT manufacturer_name FROM user_credentials"
    repaired_sql = """
        SELECT manufacturer_name, total_sales_units AS total_sales
        FROM ads_nev_manufacturer_sales_rank
        WHERE stat_year = 2022
        ORDER BY sales_rank
    """
    ask_service = _build_service(bad_sql, repaired_sqls=[repaired_sql])
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "2022 年各厂商新能源汽车销量排名如何？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"].endswith("LIMIT 100")

    step_names = [step["name"] for step in payload["execution_steps"]]
    failed_steps = [step["name"] for step in payload["execution_steps"] if step["status"] == "failed"]
    assert step_names.count("repair_sql") == 1
    assert failed_steps == ["guard_sql"]
    assert len(ask_service.text_to_sql_service.repair_calls) == 1
    assert ask_service.text_to_sql_service.repair_calls[0]["failed_sql"] == bad_sql
    assert "not allowed" in ask_service.text_to_sql_service.repair_calls[0]["error_message"]
    assert ask_service.sql_executor.executed_sql == payload["sql"]


def test_ask_api_repairs_sql_when_doris_execution_fails_first_time():
    bad_sql = """
        SELECT unknown_column AS total_sales
        FROM ads_nev_manufacturer_sales_rank
    """
    repaired_sql = """
        SELECT manufacturer_name, total_sales_units AS total_sales
        FROM ads_nev_manufacturer_sales_rank
        WHERE stat_year = 2022
        ORDER BY sales_rank
    """
    ask_service = _build_service(
        bad_sql,
        repaired_sqls=[repaired_sql],
        executor_failures=["Unknown column 'unknown_column'"],
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "2022 年各厂商新能源汽车销量排名如何？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True

    failed_steps = [step["name"] for step in payload["execution_steps"] if step["status"] == "failed"]
    assert failed_steps == ["execute_sql"]
    assert [step["name"] for step in payload["execution_steps"]].count("repair_sql") == 1
    assert len(ask_service.sql_executor.executed_sqls) == 2
    assert len(ask_service.text_to_sql_service.repair_calls) == 1
    assert "unknown_column" in ask_service.text_to_sql_service.repair_calls[0]["failed_sql"]
    assert "Unknown column" in ask_service.text_to_sql_service.repair_calls[0]["error_message"]


def test_ask_api_stops_sql_repair_after_max_attempts():
    bad_sql = "SELECT manufacturer_name FROM user_credentials"
    ask_service = _build_service(
        bad_sql,
        repaired_sqls=[
            "SELECT manufacturer_name FROM user_credentials",
            "SELECT secret FROM user_credentials",
        ],
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "2022 年各厂商新能源汽车销量排名如何？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["sql"] is None

    step_names = [step["name"] for step in payload["execution_steps"]]
    failed_steps = [step["name"] for step in payload["execution_steps"] if step["status"] == "failed"]
    assert step_names.count("repair_sql") == 2
    assert failed_steps == ["guard_sql", "guard_sql", "guard_sql"]
    assert len(ask_service.text_to_sql_service.repair_calls) == 2
    assert ask_service.sql_executor.executed_sql is None
    assert ask_service.history_service.failure_records[0]["sql"] == "SELECT secret FROM user_credentials"


def test_ask_api_rechecks_dangerous_repaired_sql_with_guard():
    bad_sql = "SELECT manufacturer_name FROM user_credentials"
    dangerous_repair = "DROP TABLE ads_nev_manufacturer_sales_rank"
    ask_service = _build_service(
        bad_sql,
        repaired_sqls=[dangerous_repair, dangerous_repair],
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "2022 年各厂商新能源汽车销量排名如何？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert ask_service.sql_executor.executed_sql is None
    assert len(ask_service.text_to_sql_service.repair_calls) == 2
    assert ask_service.text_to_sql_service.repair_calls[1]["failed_sql"] == dangerous_repair
    assert "Only SELECT statements are allowed" in payload["error_message"]


def test_ask_api_handles_latest_date_metadata_query_as_data_query():
    ask_service = _build_service(
        "SELECT MAX(data_month) FROM dws_vehicle_sales_monthly"
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post(
            "/api/ask",
            json={"query": "你的知识库，最新的是哪一天？"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert len(ask_service.text_to_sql_service.calls) == 1
    assert ask_service.text_to_sql_service.calls[0][0] == "你的知识库，最新的是哪一天？"


def test_ask_stream_api_emits_steps_and_result():
    ask_service = _build_service(
        """
        SELECT manufacturer_name, total_sales_units AS total_sales
        FROM ads_nev_manufacturer_sales_rank
        WHERE stat_year = 2022
        ORDER BY sales_rank
        """
    )
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post(
            "/api/ask/stream",
            json={"query": "2022 年各厂商新能源汽车销量排名如何？"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = [
        json.loads(chunk.removeprefix("data: "))
        for chunk in response.text.strip().split("\n\n")
        if chunk.startswith("data: ")
    ]

    assert events[0]["type"] == "step_start"
    assert events[0]["data"]["name"] == "intent_check"
    assert events[0]["data"]["status"] == "running"
    assert events[1]["type"] == "step"
    assert events[1]["data"]["name"] == "intent_check"
    assert events[1]["data"]["status"] == "success"
    assert events[-1]["type"] == "result"
    assert events[-1]["data"]["success"] is True
    assert events[-1]["data"]["chart_suggestion"]["y_axes"] == ["total_sales"]


def test_ask_api_records_failure_when_sql_guard_rejects_query():
    dangerous_sql = "DROP TABLE ads_nev_manufacturer_sales_rank"
    ask_service = _build_service(dangerous_sql)
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "删除所有数据"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["sql"] is None
    assert payload["result"] is None
    assert payload["chart_suggestion"] is None
    assert "SELECT" in payload["error_message"]
    assert payload["execution_steps"][-2]["name"] == "record_failure"
    failed_steps = [step for step in payload["execution_steps"] if step["status"] == "failed"]
    assert [step["name"] for step in failed_steps] == ["guard_sql", "guard_sql", "guard_sql"]
    assert [step["name"] for step in payload["execution_steps"]].count("repair_sql") == 2

    assert ask_service.sql_executor.executed_sql is None
    assert len(ask_service.text_to_sql_service.repair_calls) == 2
    assert len(ask_service.history_service.failure_records) == 1
    failure_record = ask_service.history_service.failure_records[0]
    assert failure_record["question"] == "删除所有数据"
    assert failure_record["error_message"] == payload["error_message"]
    assert failure_record["sql"] == dangerous_sql
    assert failure_record["execution_time_ms"] >= 0


def test_ask_api_answers_capability_question_without_calling_text_to_sql():
    ask_service = _build_service("SELECT 1")
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "我可以查询什么信息？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert payload["chart_suggestion"] is None
    assert payload["result"]["columns"] == ["table_name", "business_scope"]
    assert [
        "ads_nev_manufacturer_sales_rank",
        "新能源厂商销量排名应用表：年度厂商销量排名、头部厂商对比",
    ] in payload["result"]["rows"]
    assert "可以查询" in payload["analysis"]
    assert [step["name"] for step in payload["execution_steps"]] == [
        "intent_check",
        "daily_qa",
        "record_success",
        "build_response",
    ]

    assert ask_service.rag_service.queries == []
    assert ask_service.text_to_sql_service.calls == []
    assert ask_service.sql_executor.executed_sql is None
    assert ask_service.history_service.success_records[0]["question"] == "我可以查询什么信息？"
    assert ask_service.history_service.success_records[0]["sql"] is None
    assert ask_service.history_service.success_records[0]["row_count"] == len(payload["result"]["rows"])
    assert ask_service.history_service.success_records[0]["chart_type"] is None


def test_ask_api_answers_alternative_capability_wording_without_text_to_sql():
    ask_service = _build_service("SELECT 1")
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "有哪些数据可以查？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert "可以查询" in payload["analysis"]
    assert ask_service.text_to_sql_service.calls == []
    assert ask_service.sql_executor.executed_sql is None


def test_ask_api_answers_greeting_without_calling_text_to_sql():
    ask_service = _build_service("SELECT 1")
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "你好"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert payload["chart_suggestion"] is None
    assert "AutoBI" in payload["analysis"]
    assert ask_service.rag_service.queries == []
    assert ask_service.text_to_sql_service.calls == []
    assert ask_service.sql_executor.executed_sql is None


def test_ask_api_answers_identity_question_without_calling_text_to_sql():
    ask_service = _build_service("SELECT 1")
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "你能做什么？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert "AutoBI" in payload["analysis"]
    assert ask_service.text_to_sql_service.calls == []
    assert ask_service.sql_executor.executed_sql is None


def test_ask_api_answers_out_of_scope_question_by_calling_llm_classifier():
    ask_service = _build_service("SELECT 1")
    app.dependency_overrides[get_ask_service] = _override_service(ask_service)
    client = ASGITestClient()

    try:
        response = client.post("/api/ask", json={"query": "今天天气怎么样？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert payload["chart_suggestion"] is None
    assert "汽车产业相关数据" in payload["analysis"]
    assert [step["name"] for step in payload["execution_steps"]] == [
        "intent_check",
        "route_table",
        "retrieve_context",
        "generate_sql",
        "record_success",
        "build_response",
    ]
    assert ask_service.rag_service.table_queries == [["ads_nev_manufacturer_sales_rank"]]
    assert len(ask_service.text_to_sql_service.calls) == 1
    assert ask_service.sql_executor.executed_sql is None


def test_daily_qa_does_not_require_llm_services(monkeypatch):
    class ExplodingLLMService:
        def __init__(self):
            raise AssertionError("LLM service should not be initialized")

    monkeypatch.setattr("app.graphs.ask_graph.TextToSQLService", ExplodingLLMService)
    monkeypatch.setattr("app.graphs.ask_graph.AnalysisService", ExplodingLLMService)

    ask_service = AskService(history_service=FakeHistoryService())
    response = ask_service.run("你是谁？")

    assert response.success is True
    assert response.sql is None
    assert response.result.columns == ["table_name", "business_scope"]
