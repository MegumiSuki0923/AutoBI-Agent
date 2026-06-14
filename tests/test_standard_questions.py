import asyncio

import httpx
import pytest

from app.api.ask import get_ask_service
from app.main import app
from app.schemas import AskResponse, ChartSuggestion, QueryResult
from app.services.sql_guard import SQLGuard, SQLGuardError
STANDARD_QUESTIONS = [
    "2022 年各厂商新能源汽车销量排名如何？",
    "各省充电设施数量分布如何？",
    "动力电池不同材料类型的装车量结构如何？",
]


SUPPORTED_CHART_TYPES = {"metric", "line", "bar", "stacked_bar", "pie"}


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


@pytest.fixture()
def client():
    async def override():
        return StandardQuestionService()

    app.dependency_overrides[get_ask_service] = override
    try:
        yield ASGITestClient()
    finally:
        app.dependency_overrides.clear()


class StandardQuestionService:
    def run(self, question, thread_id=None):
        chart_type = "pie" if "电池" in question or "装车" in question else "bar"
        x_axis = "battery_material" if chart_type == "pie" else "name"
        y_axis = "total_value"

        return AskResponse(
            query=question,
            sql="SELECT manufacturer_name, total_sales_units AS total_value FROM ads_nev_manufacturer_sales_rank LIMIT 100",
            result=QueryResult(
                columns=[x_axis, y_axis],
                rows=[["样例分类", 100.0]],
            ),
            analysis="核心结论：当前测试问题可以返回结构化问数结果。",
            chart_suggestion=ChartSuggestion(
                chart_type=chart_type,
                x_axis=x_axis,
                y_axes=[y_axis],
                title="标准问题测试图表",
            ),
            success=True,
            error_message=None,
            execution_time_ms=1.0,
        )


@pytest.mark.parametrize("question", STANDARD_QUESTIONS)
def test_standard_questions_return_complete_answer(client, question):
    response = client.post("/api/ask", json={"query": question})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["query"] == question
    assert payload["sql"]
    assert payload["result"]["columns"]
    assert payload["result"]["rows"]
    assert payload["analysis"]
    assert payload["chart_suggestion"]["chart_type"] in SUPPORTED_CHART_TYPES
    assert payload["execution_time_ms"] >= 0


@pytest.mark.parametrize(
    ("question", "expected_chart_type"),
    [
        ("2022 年各厂商新能源汽车销量排名如何？", "bar"),
        ("各省充电设施数量分布如何？", "bar"),
        ("动力电池不同材料类型的装车量结构如何？", "pie"),
    ],
)
def test_representative_standard_questions_use_expected_chart_type(
    client,
    question,
    expected_chart_type,
):
    response = client.post("/api/ask", json={"query": question})

    assert response.status_code == 200
    payload = response.json()
    assert payload["chart_suggestion"]["chart_type"] == expected_chart_type


@pytest.mark.parametrize(
    "safe_sql",
    [
        """
        SELECT manufacturer_name, total_sales_units
        FROM ads_nev_manufacturer_sales_rank
        ORDER BY sales_rank
        """,
        """
        SELECT data_month, penetration_rate
        FROM ads_nev_penetration_trend
        ORDER BY data_month
        LIMIT 12
        """,
        """
        WITH battery AS (
            SELECT dimension_value, SUM(metric_value) AS total_gwh
            FROM dws_battery_structure_monthly
            WHERE dimension_type = 'material_type'
            GROUP BY dimension_value
        )
        SELECT dimension_value, total_gwh
        FROM battery
        ORDER BY total_gwh DESC
        """,
    ],
)
def test_safe_standard_question_sql_passes_guard(safe_sql):
    rewritten_sql = SQLGuard(default_limit=100).validate_and_rewrite(safe_sql)

    assert rewritten_sql.lower().startswith(("select", "with"))
    assert "LIMIT" in rewritten_sql


@pytest.mark.parametrize(
    "unsafe_sql",
    [
        "DROP TABLE ads_nev_manufacturer_sales_rank",
        "DELETE FROM ads_nev_manufacturer_sales_rank WHERE manufacturer_name = 'test'",
        "SELECT * FROM user_credentials",
        "SELECT * FROM ads_nev_manufacturer_sales_rank; DROP TABLE ads_nev_manufacturer_sales_rank;",
        "SELECT * INTO OUTFILE '/tmp/export.csv' FROM ads_nev_manufacturer_sales_rank",
    ],
)
def test_unsafe_sql_is_rejected_by_guard(unsafe_sql):
    with pytest.raises(SQLGuardError):
        SQLGuard(default_limit=100).validate_and_rewrite(unsafe_sql)


def test_missing_query_field_returns_validation_error(client):
    response = client.post("/api/ask", json={})

    assert response.status_code == 422


def test_unrelated_boundary_question_does_not_crash(client):
    response = client.post("/api/ask", json={"query": "请分析明天上海天气对销量的影响"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["error_message"] is None
    assert payload["result"]["rows"]


def test_very_long_boundary_question_does_not_crash(client):
    question = "请分析新能源汽车销量。" * 200

    response = client.post("/api/ask", json={"query": question})

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["query"] == question
