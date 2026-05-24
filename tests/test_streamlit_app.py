from unittest.mock import MagicMock

import pandas as pd

from frontend.streamlit_app import (
    BUSINESS_QUERY_SCOPES,
    QUERY_SCOPE_TITLE,
    STANDARD_QUESTIONS,
    _build_pie_chart,
    _build_x_axis_encoding,
    build_result_dataframe,
    call_ask_api,
    st,
)


def test_query_scope_title_replaces_standard_questions_label():
    assert QUERY_SCOPE_TITLE == "业务查询范围"


def test_business_query_scopes_show_current_business_tables():
    labels = [scope["label"] for scope in BUSINESS_QUERY_SCOPES]
    table_names = [scope["table_name"] for scope in BUSINESS_QUERY_SCOPES]

    assert labels == [
        "汽车品牌车型月度产销表",
        "新能源厂商月度产销表",
        "新能源总体月度产销表",
        "充电设施月度指标表",
        "动力电池月度装车指标表",
    ]
    assert table_names == [
        "fact_vehicle_prod_sales_monthly",
        "fact_nev_manufacturer_monthly",
        "fact_nev_overall_monthly",
        "fact_charging_infrastructure_monthly",
        "fact_battery_installation_monthly",
    ]


def test_standard_questions_cover_main_business_topics():
    joined = "\n".join(STANDARD_QUESTIONS)

    assert len(STANDARD_QUESTIONS) >= 5
    assert "销量" in joined
    assert "渗透率" in joined
    assert "充电" in joined
    assert "电池" in joined


def test_build_result_dataframe_from_api_result():
    df = build_result_dataframe(
        {
            "columns": ["brand", "total_sales"],
            "rows": [["比亚迪", 1860000], ["特斯拉", 710000]],
        }
    )

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["brand", "total_sales"]
    assert df.iloc[0]["brand"] == "比亚迪"
    assert df.iloc[1]["total_sales"] == 710000


def test_call_ask_api_posts_query(monkeypatch):
    response = MagicMock()
    response.json.return_value = {
        "success": True,
        "query": "查询销量",
        "sql": "SELECT 1",
    }
    response.raise_for_status.return_value = None

    post = MagicMock(return_value=response)
    monkeypatch.setattr("frontend.streamlit_app.requests.post", post)

    payload = call_ask_api("查询销量", api_url="http://testserver/api/ask")

    post.assert_called_once_with(
        "http://testserver/api/ask",
        json={"query": "查询销量"},
        timeout=60,
    )
    assert payload["success"] is True
    assert payload["sql"] == "SELECT 1"


def test_x_axis_labels_are_horizontal():
    encoding = _build_x_axis_encoding("brand").to_dict()

    assert encoding["axis"]["labelAngle"] == 0


def test_build_pie_chart_uses_arc_mark():
    df = pd.DataFrame(
        {
            "battery_material": ["磷酸铁锂", "三元锂"],
            "total_capacity": [183.8, 110.4],
        }
    )

    chart = _build_pie_chart(
        df=df,
        x_axis="battery_material",
        y_axis="total_capacity",
        title="动力电池材料装车量结构占比",
    )
    spec = chart.to_dict()

    assert spec["mark"]["type"] == "arc"
    assert spec["encoding"]["color"]["field"] == "battery_material"
    assert spec["encoding"]["theta"]["field"] == "total_capacity"
