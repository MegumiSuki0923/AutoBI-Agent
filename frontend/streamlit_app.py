from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import altair as alt
import duckdb
import pandas as pd
import requests
import streamlit as st


DEFAULT_API_URL = "http://127.0.0.1:8000/api/ask"
DB_PATH = "data/autobi.duckdb"
QUERY_SCOPE_TITLE = "业务查询范围"

BUSINESS_QUERY_SCOPES = [
    {
        "label": "汽车品牌车型月度产销表",
        "table_name": "fact_vehicle_prod_sales_monthly",
        "question": "2022 年各车型销量 Top 5 是什么？",
    },
    {
        "label": "新能源厂商月度产销表",
        "table_name": "fact_nev_manufacturer_monthly",
        "question": "2022 年各厂商新能源汽车销量排名如何？",
    },
    {
        "label": "新能源总体月度产销表",
        "table_name": "fact_nev_overall_monthly",
        "question": "新能源汽车渗透率的月度变化趋势如何？",
    },
    {
        "label": "充电设施月度指标表",
        "table_name": "fact_charging_infrastructure_monthly",
        "question": "各省充电设施数量分布如何？",
    },
    {
        "label": "动力电池月度装车指标表",
        "table_name": "fact_battery_installation_monthly",
        "question": "动力电池不同材料类型的装车量结构如何？",
    },
]

STANDARD_QUESTIONS = [scope["question"] for scope in BUSINESS_QUERY_SCOPES]


def call_ask_api(
    query: str,
    api_url: str = DEFAULT_API_URL,
    timeout: int = 60,
) -> Dict[str, Any]:
    response = requests.post(api_url, json={"query": query}, timeout=timeout)
    response.raise_for_status()
    return response.json()


def build_result_dataframe(result: Optional[Dict[str, Any]]) -> pd.DataFrame:
    if not result:
        return pd.DataFrame()

    columns = result.get("columns") or []
    rows = result.get("rows") or []
    return pd.DataFrame(rows, columns=columns)


def main() -> None:
    st.set_page_config(
        page_title="AutoBI Agent",
        page_icon="📊",
        layout="wide",
    )

    if st.session_state.get("current_page") == "table_detail":
        _render_table_detail_page()
        return

    st.title("AutoBI Agent")
    st.caption("面向汽车产业数据的智能问数助手")

    api_url = _render_sidebar()
    _init_session_state()
    _render_standard_question_buttons()

    with st.form("ask_form", clear_on_submit=False):
        query = st.text_area(
            "业务问题",
            key="question",
            height=88,
            placeholder="例如：2022 年各厂商新能源汽车销量排名如何？",
        )
        submitted = st.form_submit_button("查询", type="primary", use_container_width=True)

    if submitted:
        _handle_query(query=query, api_url=api_url)

    if "last_response" in st.session_state:
        _render_response(st.session_state["last_response"])


def _render_sidebar() -> str:
    with st.sidebar:
        st.header("连接设置")
        api_url = st.text_input(
            "后端 API 地址",
            value=os.getenv("AUTOBI_API_URL", DEFAULT_API_URL),
            help="默认连接本地 FastAPI: http://127.0.0.1:8000/api/ask",
        )
        st.divider()
        st.caption("先启动 FastAPI 后端，再在这里提交问题。")
    return api_url.strip() or DEFAULT_API_URL


def _init_session_state() -> None:
    if "question" not in st.session_state:
        st.session_state["question"] = STANDARD_QUESTIONS[0]


def _render_standard_question_buttons() -> None:
    st.subheader(QUERY_SCOPE_TITLE)
    for index, scope in enumerate(BUSINESS_QUERY_SCOPES):
        if index % 3 == 0:
            cols = st.columns(3)
        with cols[index % 3]:
            if st.button(
                scope["label"],
                key=f"scope_button_{index}",
                help=f"点击查看 {scope['table_name']} 表数据",
                use_container_width=True,
            ):
                st.session_state["current_page"] = "table_detail"
                st.session_state["selected_scope"] = scope
                st.rerun()


def _render_table_detail_page() -> None:
    """展示单张业务表的数据预览页面。"""
    scope = st.session_state.get("selected_scope")
    if not scope:
        st.session_state.pop("current_page", None)
        st.rerun()
        return

    if st.button("← 返回首页"):
        st.session_state.pop("current_page", None)
        st.session_state.pop("selected_scope", None)
        st.rerun()

    table_name = scope["table_name"]
    st.title(scope["label"])
    st.caption(f"数据表：`{table_name}`")

    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
        total_rows = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        col_info = conn.execute(f"DESCRIBE {table_name}").df()
        df = conn.execute(f"SELECT * FROM {table_name}").df()
        conn.close()

        info_col, _ = st.columns([1, 3])
        with info_col:
            st.metric("总行数", f"{total_rows:,}")

        with st.expander("字段信息", expanded=False):
            st.dataframe(col_info, use_container_width=True, hide_index=True)

        st.subheader("数据详情")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("推荐问题")
        st.info(f"💡 {scope['question']}")

    except Exception as exc:
        st.error(f"查询表数据失败：{exc}")


def _handle_query(query: str, api_url: str) -> None:
    cleaned_query = query.strip()
    if not cleaned_query:
        st.warning("请输入业务问题。")
        return

    with st.spinner("正在查询..."):
        try:
            payload = call_ask_api(cleaned_query, api_url=api_url)
        except requests.RequestException as exc:
            st.error(f"后端请求失败：{exc}")
            return

    st.session_state["last_response"] = payload


def _render_response(payload: Dict[str, Any]) -> None:
    if not payload.get("success", False):
        st.error(payload.get("error_message") or "查询失败。")
        return

    sql = payload.get("sql")
    result = payload.get("result")
    analysis = payload.get("analysis")
    chart_suggestion = payload.get("chart_suggestion")
    execution_time = payload.get("execution_time_ms")

    metric_col, status_col = st.columns([1, 3])
    with metric_col:
        if execution_time is not None:
            st.metric("执行耗时", f"{execution_time} ms")
    with status_col:
        st.success("查询完成")

    if sql:
        with st.expander("SQL", expanded=True):
            st.code(sql, language="sql")

    df = build_result_dataframe(result)
    if not df.empty:
        st.subheader("查询结果")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("图表")
        _render_chart(df, chart_suggestion)
    elif sql:
        st.info("当前查询结果为空。")

    if analysis:
        st.subheader("分析结论")
        st.markdown(analysis)


def _render_chart(df: pd.DataFrame, chart_suggestion: Optional[Dict[str, Any]]) -> None:
    if not chart_suggestion:
        st.info("暂无图表推荐。")
        return

    chart_type = chart_suggestion.get("chart_type")
    x_axis = chart_suggestion.get("x_axis")
    y_axes = chart_suggestion.get("y_axes") or []
    title = chart_suggestion.get("title") or "推荐图表"

    missing_y_axes = [axis for axis in y_axes if axis not in df.columns]
    if missing_y_axes:
        st.warning(f"图表字段不存在：{', '.join(missing_y_axes)}")
        return

    if chart_type == "metric":
        _render_metric_card(df, y_axes, title)
    elif chart_type == "line":
        _render_line_chart(df, x_axis, y_axes)
    elif chart_type == "bar":
        _render_bar_chart(df, x_axis, y_axes)
    elif chart_type == "stacked_bar":
        _render_stacked_bar_chart(df, x_axis, y_axes, title)
    elif chart_type == "pie":
        _render_pie_chart(df, x_axis, y_axes, title)
    else:
        st.warning(f"暂不支持图表类型：{chart_type}")


def _render_metric_card(df: pd.DataFrame, y_axes: List[str], title: str) -> None:
    if not y_axes or df.empty:
        st.info("指标卡缺少可展示数值。")
        return

    value = df.iloc[0][y_axes[0]]
    st.metric(title, value)


def _render_line_chart(df: pd.DataFrame, x_axis: Optional[str], y_axes: List[str]) -> None:
    if not _can_use_axes(df, x_axis, y_axes):
        return

    chart = _build_multi_series_chart(
        df=df,
        x_axis=x_axis,
        y_axes=y_axes,
        mark="line",
    )
    st.altair_chart(chart, use_container_width=True)


def _render_bar_chart(df: pd.DataFrame, x_axis: Optional[str], y_axes: List[str]) -> None:
    if not _can_use_axes(df, x_axis, y_axes):
        return

    chart = _build_multi_series_chart(
        df=df,
        x_axis=x_axis,
        y_axes=y_axes,
        mark="bar",
    )
    st.altair_chart(chart, use_container_width=True)


def _render_stacked_bar_chart(
    df: pd.DataFrame,
    x_axis: Optional[str],
    y_axes: List[str],
    title: str,
) -> None:
    if not x_axis or x_axis not in df.columns or not y_axes:
        st.info("堆叠柱状图缺少横轴或数值字段。")
        return

    if len(y_axes) == 1:
        color_axis = _pick_color_axis(df, x_axis=x_axis, y_axis=y_axes[0])
        if not color_axis:
            _render_bar_chart(df, x_axis, y_axes)
            return

        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=_build_x_axis_encoding(x_axis),
                y=alt.Y(f"{y_axes[0]}:Q", title=y_axes[0]),
                color=alt.Color(f"{color_axis}:N", title=color_axis),
                tooltip=[x_axis, color_axis, y_axes[0]],
            )
            .properties(title=title)
        )
    else:
        melted = df.melt(
            id_vars=[x_axis],
            value_vars=y_axes,
            var_name="series",
            value_name="value",
        )
        chart = (
            alt.Chart(melted)
            .mark_bar()
            .encode(
                x=_build_x_axis_encoding(x_axis),
                y=alt.Y("value:Q", title="value"),
                color=alt.Color("series:N", title="series"),
                tooltip=[x_axis, "series", "value"],
            )
            .properties(title=title)
        )

    st.altair_chart(chart, use_container_width=True)


def _render_pie_chart(
    df: pd.DataFrame,
    x_axis: Optional[str],
    y_axes: List[str],
    title: str,
) -> None:
    if not x_axis or x_axis not in df.columns or not y_axes:
        st.info("饼图缺少分类字段或数值字段。")
        return

    chart = _build_pie_chart(
        df=df,
        x_axis=x_axis,
        y_axis=y_axes[0],
        title=title,
    )
    st.altair_chart(chart, use_container_width=True)


def _can_use_axes(df: pd.DataFrame, x_axis: Optional[str], y_axes: List[str]) -> bool:
    if not x_axis or x_axis not in df.columns:
        st.info("图表缺少可用横轴。")
        return False
    if not y_axes:
        st.info("图表缺少可用数值字段。")
        return False
    return True


def _build_multi_series_chart(
    df: pd.DataFrame,
    x_axis: str,
    y_axes: List[str],
    mark: str,
) -> alt.Chart:
    chart_df = df[[x_axis, *y_axes]].copy()
    for axis in y_axes:
        chart_df[axis] = pd.to_numeric(chart_df[axis], errors="coerce")

    if len(y_axes) == 1:
        base = alt.Chart(chart_df)
        mark_method = base.mark_line if mark == "line" else base.mark_bar
        return mark_method().encode(
            x=_build_x_axis_encoding(x_axis),
            y=alt.Y(f"{y_axes[0]}:Q", title=y_axes[0]),
            tooltip=[x_axis, y_axes[0]],
        )

    melted = chart_df.melt(
        id_vars=[x_axis],
        value_vars=y_axes,
        var_name="series",
        value_name="value",
    )
    base = alt.Chart(melted)
    mark_method = base.mark_line if mark == "line" else base.mark_bar
    return mark_method().encode(
        x=_build_x_axis_encoding(x_axis),
        y=alt.Y("value:Q", title="value"),
        color=alt.Color("series:N", title="series"),
        tooltip=[x_axis, "series", "value"],
    )


def _build_x_axis_encoding(x_axis: str) -> alt.X:
    return alt.X(
        f"{x_axis}:N",
        title=x_axis,
        axis=alt.Axis(labelAngle=0),
    )


def _build_pie_chart(
    df: pd.DataFrame,
    x_axis: str,
    y_axis: str,
    title: str,
) -> alt.Chart:
    chart_df = df[[x_axis, y_axis]].copy()
    chart_df[y_axis] = pd.to_numeric(chart_df[y_axis], errors="coerce")
    return (
        alt.Chart(chart_df)
        .mark_arc()
        .encode(
            theta=alt.Theta(f"{y_axis}:Q", title=y_axis),
            color=alt.Color(f"{x_axis}:N", title=x_axis),
            tooltip=[x_axis, y_axis],
        )
        .properties(title=title)
    )


def _pick_color_axis(df: pd.DataFrame, x_axis: str, y_axis: str) -> Optional[str]:
    for column in df.columns:
        if column not in {x_axis, y_axis}:
            return column
    return None


if __name__ == "__main__":
    main()
