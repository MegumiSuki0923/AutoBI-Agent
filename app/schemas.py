from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(
        ...,
        description="用户输入的关于汽车产业数据的自然语言提问",
        example="2022 年各厂商新能源汽车销量排名如何？"
    )
    thread_id: Optional[str] = Field(
        None,
        description="会话ID，用于多轮对话历史关联（如不传则不关联历史）",
        example="session-12345"
    )

class ChartSuggestion(BaseModel):
    chart_type: str = Field(
        ...,
        description="推荐的图表可视化类型（如：line 折线图, bar 柱状图, stacked_bar 堆叠柱状图, pie 饼图, metric 指标卡）",
        example="bar"
    )
    x_axis: Optional[str] = Field(
        None,
        description="推荐作为 X 轴（横坐标）的字段名",
        example="厂商"
    )
    y_axes: Optional[List[str]] = Field(
        None,
        description="推荐作为 Y 轴（纵坐标）的字段名列表",
        example=["销量"]
    )
    title: Optional[str] = Field(
        None,
        description="推荐的图表标题",
        example="2022年新能源汽车销量排名"
    )

class QueryResult(BaseModel):
    columns: List[str] = Field(
        ...,
        description="查询结果的列名（表头）列表",
        example=["厂商", "销量"]
    )
    rows: List[List[Any]] = Field(
        ...,
        description="查询结果的行数据列表（每一行是一个值列表）",
        example=[["比亚迪", 1860000], ["特斯拉", 710000], ["广汽埃安", 270000]]
    )


class ExecutionStep(BaseModel):
    name: str = Field(
        ...,
        description="执行步骤名称，例如 intent_check、generate_sql、execute_sql",
        example="generate_sql",
    )
    status: str = Field(
        ...,
        description="执行步骤状态，例如 success、failed",
        example="success",
    )
    message: str = Field(
        ...,
        description="执行步骤的简要说明",
        example="已生成候选 SQL",
    )
    elapsed_ms: float = Field(
        ...,
        description="该步骤自身耗时，单位毫秒",
        example=12.34,
    )


class AskResponse(BaseModel):
    query: str = Field(
        ...,
        description="原始的用户自然语言提问"
    )
    sql: Optional[str] = Field(
        None,
        description="AI 翻译生成并通过安全校验的 SQL 查询语句"
    )
    result: Optional[QueryResult] = Field(
        None,
        description="数据库实际执行 SQL 后返回的二维表结果"
    )
    analysis: Optional[str] = Field(
        None,
        description="AI 结合查询数据生成的商业智能分析结论"
    )
    chart_suggestion: Optional[ChartSuggestion] = Field(
        None,
        description="针对查询结果的数据可视化推荐图表配置"
    )
    success: bool = Field(
        ...,
        description="请求处理是否成功"
    )
    error_message: Optional[str] = Field(
        None,
        description="当处理失败时的详细错误说明信息"
    )
    execution_time_ms: float = Field(
        ...,
        description="整个接口在后端链路中处理消耗的时间（毫秒）"
    )
    execution_steps: List[ExecutionStep] = Field(
        default_factory=list,
        description="后端 Agent 编排链路中已经执行的步骤",
    )
