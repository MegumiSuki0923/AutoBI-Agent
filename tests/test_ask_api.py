from fastapi.testclient import TestClient

from app.api.ask import AskPipeline, get_ask_pipeline
from app.main import app
from app.schemas import ChartSuggestion
from app.services.sql_guard import SQLGuard


class FakeRAGService:
    def __init__(self):
        self.queries = []

    def retrieve(self, query, limit=3):
        self.queries.append((query, limit))
        return [
            {
                "source": "data_dictionary.md",
                "title": "fact_nev_manufacturer_monthly",
                "content": "字段: manufacturer_name, sales_current_units",
            },
            {
                "source": "metrics.md",
                "title": "厂商销量排名",
                "content": "SUM(sales_current_units) AS total_sales",
            },
        ]


class FakeTextToSQLService:
    def __init__(self, sql):
        self.sql = sql
        self.calls = []

    def generate_sql(self, question, schema_context, metric_context):
        self.calls.append((question, schema_context, metric_context))
        if "天气" in question or "闲聊" in question:
            return False, None, "超出了数据库表范围。", "很抱歉，我目前仅支持汽车产业相关数据的智能问数，无法回答天气或闲聊类问题。"
        return True, self.sql, "按数据结构查询。", None


class FakeSQLExecutor:
    def __init__(self):
        self.executed_sql = None

    def execute(self, sql):
        self.executed_sql = sql
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
    def __init__(self):
        self.success_records = []
        self.failure_records = []

    def record_success(self, **kwargs):
        self.success_records.append(kwargs)
        return 1

    def record_failure(self, **kwargs):
        self.failure_records.append(kwargs)
        return 1


def _build_pipeline(sql):
    rag_service = FakeRAGService()
    text_to_sql_service = FakeTextToSQLService(sql)
    sql_executor = FakeSQLExecutor()
    chart_service = FakeChartService()
    analysis_service = FakeAnalysisService()
    history_service = FakeHistoryService()
    pipeline = AskPipeline(
        rag_service=rag_service,
        text_to_sql_service=text_to_sql_service,
        sql_guard=SQLGuard(default_limit=100),
        sql_executor=sql_executor,
        chart_service=chart_service,
        analysis_service=analysis_service,
        history_service=history_service,
    )
    return pipeline


def test_ask_api_runs_real_pipeline_with_safe_sql():
    pipeline = _build_pipeline(
        """
        SELECT manufacturer_name, SUM(sales_current_units) AS total_sales
        FROM fact_nev_manufacturer_monthly
        GROUP BY manufacturer_name
        ORDER BY total_sales DESC
        """
    )
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

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

    assert pipeline.rag_service.queries == [
        ("2022 年各厂商新能源汽车销量排名如何？", 6)
    ]
    assert "fact_nev_manufacturer_monthly" in pipeline.text_to_sql_service.calls[0][1]
    assert "SUM(sales_current_units)" in pipeline.text_to_sql_service.calls[0][2]
    assert pipeline.sql_executor.executed_sql == payload["sql"]
    assert pipeline.history_service.success_records[0]["question"] == payload["query"]
    assert pipeline.history_service.success_records[0]["sql"] == payload["sql"]
    assert pipeline.history_service.success_records[0]["row_count"] == 1
    assert pipeline.history_service.success_records[0]["chart_type"] == "bar"


def test_ask_api_handles_latest_date_metadata_query_as_data_query():
    pipeline = _build_pipeline(
        "SELECT MAX(CAST(data_month AS DATE)) FROM fact_vehicle_prod_sales_monthly"
    )
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

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
    assert len(pipeline.text_to_sql_service.calls) == 1
    assert pipeline.text_to_sql_service.calls[0][0] == "你的知识库，最新的是哪一天？"


def test_ask_api_records_failure_when_sql_guard_rejects_query():
    dangerous_sql = "DROP TABLE fact_nev_manufacturer_monthly"
    pipeline = _build_pipeline(dangerous_sql)
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

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

    assert pipeline.sql_executor.executed_sql is None
    assert pipeline.history_service.failure_records == [
        {
            "question": "删除所有数据",
            "error_message": payload["error_message"],
            "sql": dangerous_sql,
            "execution_time_ms": payload["execution_time_ms"],
        }
    ]


def test_ask_api_answers_capability_question_without_calling_text_to_sql():
    pipeline = _build_pipeline("SELECT 1")
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

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
        "fact_nev_manufacturer_monthly",
        "新能源厂商月度产销表：厂商销量排名、厂商销量趋势、产销对比",
    ] in payload["result"]["rows"]
    assert "可以查询" in payload["analysis"]

    assert pipeline.rag_service.queries == []
    assert pipeline.text_to_sql_service.calls == []
    assert pipeline.sql_executor.executed_sql is None
    assert pipeline.history_service.success_records[0]["question"] == "我可以查询什么信息？"
    assert pipeline.history_service.success_records[0]["sql"] is None
    assert pipeline.history_service.success_records[0]["row_count"] == len(payload["result"]["rows"])
    assert pipeline.history_service.success_records[0]["chart_type"] is None


def test_ask_api_answers_alternative_capability_wording_without_text_to_sql():
    pipeline = _build_pipeline("SELECT 1")
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

    try:
        response = client.post("/api/ask", json={"query": "有哪些数据可以查？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert "可以查询" in payload["analysis"]
    assert pipeline.text_to_sql_service.calls == []
    assert pipeline.sql_executor.executed_sql is None


def test_ask_api_answers_greeting_without_calling_text_to_sql():
    pipeline = _build_pipeline("SELECT 1")
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

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
    assert pipeline.rag_service.queries == []
    assert pipeline.text_to_sql_service.calls == []
    assert pipeline.sql_executor.executed_sql is None


def test_ask_api_answers_identity_question_without_calling_text_to_sql():
    pipeline = _build_pipeline("SELECT 1")
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

    try:
        response = client.post("/api/ask", json={"query": "你能做什么？"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["sql"] is None
    assert "AutoBI" in payload["analysis"]
    assert pipeline.text_to_sql_service.calls == []
    assert pipeline.sql_executor.executed_sql is None


def test_ask_api_answers_out_of_scope_question_by_calling_llm_classifier():
    pipeline = _build_pipeline("SELECT 1")
    app.dependency_overrides[get_ask_pipeline] = lambda: pipeline
    client = TestClient(app)

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
    assert pipeline.rag_service.queries == [("今天天气怎么样？", 6)]
    assert len(pipeline.text_to_sql_service.calls) == 1
    assert pipeline.sql_executor.executed_sql is None


def test_daily_qa_does_not_require_llm_services(monkeypatch):
    class ExplodingLLMService:
        def __init__(self):
            raise AssertionError("LLM service should not be initialized")

    monkeypatch.setattr("app.api.ask.TextToSQLService", ExplodingLLMService)
    monkeypatch.setattr("app.api.ask.AnalysisService", ExplodingLLMService)

    pipeline = AskPipeline(history_service=FakeHistoryService())
    response = pipeline.run("你是谁？")

    assert response.success is True
    assert response.sql is None
    assert response.result.columns == ["table_name", "business_scope"]
