from app.services.chart_service import ChartService


def test_recommend_metric_card_for_single_numeric_result():
    service = ChartService()

    chart = service.recommend_chart(
        question="2022 年新能源汽车总销量是多少？",
        columns=["total_sales"],
        rows=[[1860000]],
    )

    assert chart.chart_type == "metric"
    assert chart.x_axis is None
    assert chart.y_axes == ["total_sales"]
    assert "指标卡" in chart.title


def test_recommend_line_chart_for_time_series_trend():
    service = ChartService()

    chart = service.recommend_chart(
        question="新能源汽车销量的月度趋势如何？",
        columns=["data_month", "total_sales"],
        rows=[
            ["2022-01-01", 1000],
            ["2022-02-01", 1300],
            ["2022-03-01", 1600],
        ],
    )

    assert chart.chart_type == "line"
    assert chart.x_axis == "data_month"
    assert chart.y_axes == ["total_sales"]
    assert "趋势" in chart.title


def test_recommend_bar_chart_for_ranking_or_category_comparison():
    service = ChartService()

    chart = service.recommend_chart(
        question="2022 年各厂商新能源汽车销量排名如何？",
        columns=["manufacturer_name", "total_sales"],
        rows=[
            ["比亚迪", 1860000],
            ["特斯拉", 710000],
            ["广汽埃安", 271200],
        ],
    )

    assert chart.chart_type == "bar"
    assert chart.x_axis == "manufacturer_name"
    assert chart.y_axes == ["total_sales"]
    assert "对比" in chart.title


def test_recommend_stacked_bar_for_long_structure_question():
    service = ChartService()

    chart = service.recommend_chart(
        question="各月份不同燃料类型的销量结构如何？",
        columns=["data_month", "fuel_type", "sales_current_units"],
        rows=[
            ["2022-01-01", "纯电动", 900],
            ["2022-01-01", "插电式混合动力", 300],
            ["2022-02-01", "纯电动", 1000],
            ["2022-02-01", "插电式混合动力", 350],
        ],
    )

    assert chart.chart_type == "stacked_bar"
    assert chart.x_axis == "data_month"
    assert chart.y_axes == ["sales_current_units"]
    assert "结构" in chart.title


def test_recommend_stacked_bar_for_wide_series_structure():
    service = ChartService()

    chart = service.recommend_chart(
        question="不同动力类型销量结构对比",
        columns=["data_month", "bev_sales", "phev_sales"],
        rows=[
            ["2022-01-01", 900, 300],
            ["2022-02-01", 1000, 350],
        ],
    )

    assert chart.chart_type == "stacked_bar"
    assert chart.x_axis == "data_month"
    assert chart.y_axes == ["bev_sales", "phev_sales"]


def test_recommend_bar_chart_when_time_field_is_absent():
    service = ChartService()

    chart = service.recommend_chart(
        question="各省充电桩数量分布如何？",
        columns=["province", "pile_count"],
        rows=[["广东", 38500], ["江苏", 29800]],
    )

    assert chart.chart_type == "bar"
    assert chart.x_axis == "province"
    assert chart.y_axes == ["pile_count"]


def test_empty_result_does_not_recommend_metric_card():
    service = ChartService()

    chart = service.recommend_chart(
        question="2022 年新能源汽车总销量是多少？",
        columns=["total_sales"],
        rows=[],
    )

    assert chart.chart_type != "metric"


def test_time_field_defaults_to_line_even_without_trend_keyword():
    service = ChartService()

    chart = service.recommend_chart(
        question="2022 年每月各省充电桩数量",
        columns=["data_month", "province", "pile_count"],
        rows=[
            ["2022-01-01", "广东", 1000],
            ["2022-02-01", "广东", 1300],
            ["2022-03-01", "广东", 1600],
        ],
    )

    assert chart.chart_type == "line"
    assert chart.x_axis == "data_month"
    assert chart.y_axes == ["pile_count"]
