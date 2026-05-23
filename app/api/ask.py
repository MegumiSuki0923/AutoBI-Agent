import time
from fastapi import APIRouter, status
from app.schemas import AskRequest, AskResponse, QueryResult, ChartSuggestion

router = APIRouter()

@router.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
    summary="智能数据查询接口",
    description="输入自然语言业务问题，系统经过 AI 翻译、数据库查询与分析后返回结构化结果和分析建议（当前为 Mock 仿真数据阶段）。"
)
async def ask_question(payload: AskRequest) -> AskResponse:
    start_time = time.time()

    # 模拟处理延迟（为了让 execution_time_ms 看起来更真实）
    time.sleep(0.05)

    query = payload.query

    # 默认 Mock 仿真数据
    mock_sql = "SELECT brand, SUM(sales) AS total_sales FROM新能源销量表 WHERE year = 2022 GROUP BY brand ORDER BY total_sales DESC LIMIT 5;"
    mock_columns = ["brand", "total_sales"]
    mock_rows = [
        ["比亚迪", 1860000],
        ["特斯拉", 710000],
        ["广汽埃安", 271200],
        ["奇瑞汽车", 232000],
        ["吉利汽车", 224000]
    ]
    mock_analysis = (
        "2022年各厂商新能源汽车销量表现呈现出明显的梯队分化特征：\n"
        "1. 比亚迪以186万辆的绝对优势高居榜首，市场统治地位明显；\n"
        "2. 特斯拉以71万辆位列第二，作为独资品牌表现强势；\n"
        "3. 广汽埃安、奇瑞和吉利销量均在20-30万辆区间，处于第二梯队，竞争激烈。"
    )
    mock_chart = ChartSuggestion(
        chart_type="bar",
        x_axis="brand",
        y_axes=["total_sales"],
        title="2022年各厂商新能源汽车销量Top 5"
    )

    # 如果用户输入了其他问题，我们可以稍作泛化，使 Mock 体验更好
    if "充电" in query or "桩" in query:
        mock_sql = "SELECT province, COUNT(station_id) AS stations FROM 充电基础设施表 GROUP BY province ORDER BY stations DESC LIMIT 5;"
        mock_columns = ["province", "stations"]
        mock_rows = [
            ["广东", 38500],
            ["江苏", 29800],
            ["浙江", 27400],
            ["上海", 25600],
            ["北京", 22100]
        ]
        mock_analysis = (
            "从充电基础设施的地域分布来看，沿海发达省市具有明显优势：\n"
            "1. 广东省充电设施数量达3.85万个，全国领先，这与当地新能源汽车高保有量高度匹配；\n"
            "2. 江苏、浙江、上海和北京紧随其后，前五名均为经济发达、新能源推广力度大的省市。"
        )
        mock_chart = ChartSuggestion(
            chart_type="bar",
            x_axis="province",
            y_axes=["stations"],
            title="充电基础设施主要省市分布情况"
        )
    elif "电池" in query or "装车" in query:
        mock_sql = "SELECT battery_material, SUM(capacity_gwh) AS total_capacity FROM 动力电池表 GROUP BY battery_material;"
        mock_columns = ["battery_material", "total_capacity"]
        mock_rows = [
            ["磷酸铁锂", 183.8],
            ["三元锂", 110.4],
            ["其他", 0.6]
        ]
        mock_analysis = (
            "动力电池装车量数据显示，磷酸铁锂电池与三元锂电池依然占据市场绝对统治地位：\n"
            "1. 磷酸铁锂电池装车量为183.8 GWh，市场占比接近62%，凭借成本和安全优势占据主流；\n"
            "2. 三元锂电池装车量为110.4 GWh，占比约37%，主要服务于高续航车型；\n"
            "3. 其他新型材料电池尚处于起步阶段。"
        )
        mock_chart = ChartSuggestion(
            chart_type="pie",
            x_axis="battery_material",
            y_axes=["total_capacity"],
            title="动力电池材料装车量结构占比"
        )

    execution_time = (time.time() - start_time) * 1000.0

    return AskResponse(
        query=query,
        sql=mock_sql,
        result=QueryResult(columns=mock_columns, rows=mock_rows),
        analysis=mock_analysis,
        chart_suggestion=mock_chart,
        success=True,
        error_message=None,
        execution_time_ms=round(execution_time, 2)
    )
