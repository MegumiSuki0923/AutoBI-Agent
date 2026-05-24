# API 设计文档

本文档整理 AutoBI Agent 当前 FastAPI 接口设计、请求响应结构、错误约定和前后端交互方式。

## 1. 当前状态

当前 API 已实现基础问数接口和 Swagger 文档，后端入口为 `app/main.py`。

运行方式：

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档地址：

```text
http://127.0.0.1:8000/docs
```

重要说明：当前 `/api/ask` 已从 Mock 仿真返回改为真实链路编排。接口会检索数据字典和指标口径，调用 Text-to-SQL 生成 SQL，通过 SQL Guard 做执行前安全校验，查询 `data/autobi.duckdb`，再生成图表建议、分析总结并写入历史记录。

## 2. 服务边界

```text
Streamlit 前端
  -> POST /api/ask
  -> FastAPI 路由
  -> AskPipeline
  -> RAG 检索数据字典和指标口径
  -> TextToSQLService 生成 SQL
  -> SQLGuard 校验并补充 LIMIT
  -> SQLExecutor 执行 DuckDB 查询
  -> ChartService 推荐图表
  -> AnalysisService 生成分析总结
  -> HistoryService 记录成功或失败日志
  -> 返回 AskResponse
```

测试环境通过 FastAPI dependency override 替换 `AskPipeline` 或其内部服务，避免单元测试真实调用外部 LLM。

当前真实链路（混合路由）：

```text
POST /api/ask
  -> 1. 意图极速匹配：如果是极简问候语（“你好”、“谢谢”等），直接本地路由至 Daily QA 回复，跳过后续步骤。
  -> 2. 意图大模型路径：非极简问候语进入 RAG 检索数据字典和指标口径，并调用 TextToSQLService 做语义意图判定与 SQL 生成。
       ├─ 若大模型判定为非数据问题 (is_data_query = false)：
       │    ├─ 绕过 SQLGuard, SQLExecutor, ChartService, AnalysisService。
       │    └─ 由 HistoryService 记录成功，直接返回带有大模型对话回复 chat_reply 的 AskResponse（映射在 analysis 字段）。
       │
       └─ 若大模型判定为数据问题 (is_data_query = true)：
            ├─ SQLGuard 校验 SQL 并补充默认 LIMIT 100。
            ├─ SQLExecutor 执行 DuckDB 数据库查询。
            ├─ ChartService 基于字段和问题意图进行图表推荐（已修复将 monthly_sales 误判为时间轴的 Bug）。
            ├─ AnalysisService 基于数据生成核心结论、数据依据和行动建议。
            └─ HistoryService 记录成功并返回完整 AskResponse。
```

## 3. 接口清单

| 方法 | 路径 | 说明 | 当前状态 |
| --- | --- | --- | --- |
| `GET` | `/` | 服务健康检查和欢迎信息 | 已实现 |
| `POST` | `/api/ask` | 自然语言问数接口 | 已接入真实链路 |

## 4. `GET /`

### 4.1 用途

用于确认 FastAPI 服务是否启动。

### 4.2 响应示例

```json
{
  "status": "online",
  "message": "Welcome to AutoBI Agent API! Please visit /docs for interactive Swagger UI."
}
```

## 5. `POST /api/ask`

### 5.1 用途

接收用户自然语言问题，返回 SQL、查询结果、分析结论、图表建议、执行状态和耗时。

### 5.2 Request Body

模型：`AskRequest`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `query` | `string` | 是 | 用户输入的关于汽车产业数据的自然语言提问 |

请求示例：

```json
{
  "query": "动力电池不同材料类型的装车量结构如何？"
}
```

### 5.3 Response Body

模型：`AskResponse`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `query` | `string` | 原始用户问题 |
| `sql` | `string | null` | 生成并通过安全校验的 SQL |
| `result` | `QueryResult | null` | 查询结果二维表 |
| `analysis` | `string | null` | BI 分析总结 |
| `chart_suggestion` | `ChartSuggestion | null` | 图表推荐配置 |
| `success` | `boolean` | 本次请求是否成功 |
| `error_message` | `string | null` | 失败原因 |
| `execution_time_ms` | `number` | 后端链路耗时，单位毫秒 |

`QueryResult`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `columns` | `string[]` | 查询结果表头 |
| `rows` | `array[]` | 查询结果行数据 |

`ChartSuggestion`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chart_type` | `string` | 推荐图表类型：`metric`、`line`、`bar`、`stacked_bar`、`pie` |
| `x_axis` | `string | null` | 推荐横轴字段 |
| `y_axes` | `string[] | null` | 推荐纵轴字段列表 |
| `title` | `string | null` | 图表标题 |

### 5.4 成功响应示例

```json
{
  "query": "动力电池不同材料类型的装车量结构如何？",
  "sql": "SELECT dimension_value, SUM(metric_value) AS total_capacity FROM fact_battery_installation_monthly WHERE dimension_type = 'material_type' AND metric_name = '装车量' GROUP BY dimension_value ORDER BY total_capacity DESC LIMIT 100",
  "result": {
    "columns": ["dimension_value", "total_capacity"],
    "rows": [
      ["磷酸铁锂", 183.8],
      ["三元锂", 110.4],
      ["其他", 0.6]
    ]
  },
  "analysis": "动力电池装车量数据显示，磷酸铁锂电池与三元锂电池依然占据市场绝对统治地位...",
  "chart_suggestion": {
    "chart_type": "pie",
    "x_axis": "dimension_value",
    "y_axes": ["total_capacity"],
    "title": "动力电池材料装车量结构占比"
  },
  "success": true,
  "error_message": null,
  "execution_time_ms": 55.21
}
```

### 5.5 校验失败响应

当请求体缺少 `query` 字段时，FastAPI/Pydantic 返回 `422`。

示例：

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "query"],
      "msg": "Field required"
    }
  ]
}
```

业务处理失败时当前保持 HTTP 200，并通过统一响应体中的 `success=false` 和 `error_message` 表达失败原因：

```json
{
  "query": "删除所有数据",
  "sql": null,
  "result": null,
  "analysis": null,
  "chart_suggestion": null,
  "success": false,
  "error_message": "Only SELECT statements are allowed",
  "execution_time_ms": 8.9
}
```

## 6. 图表类型约定

| 图表类型 | 前端渲染 | 适用场景 |
| --- | --- | --- |
| `metric` | `st.metric` | 单行单指标 |
| `line` | Altair line chart | 时间序列趋势 |
| `bar` | Altair bar chart | 分类对比、排名 |
| `stacked_bar` | Altair stacked bar chart | 结构、占比、构成 |
| `pie` | Altair arc chart | 少量分类的结构占比 |

前端文件：`frontend/streamlit_app.py`

## 7. 安全设计

SQL 安全由两层组成：

1. Prompt 层约束：Text-to-SQL Prompt 禁止生成非只读 SQL、白名单外表和 `SELECT *`。
2. 执行前校验：`SQLGuard` 使用 `sqlglot` 解析 SQL，并强制执行：
   - 只允许单条语句。
   - 顶层必须是 SELECT。
   - 只允许访问白名单表。
   - 禁止带库名或 schema 前缀的表名。
   - 自动补充默认 `LIMIT 100`。

当前白名单表：

```text
dim_data_source
fact_vehicle_prod_sales_monthly
fact_nev_manufacturer_monthly
fact_nev_overall_monthly
fact_charging_infrastructure_monthly
fact_battery_installation_monthly
```

## 8. 历史记录

`HistoryService` 已接入 `/api/ask`，会把成功和失败记录写入内部日志表 `query_history`。当前未暴露历史记录 API。

记录字段：

```text
id
created_at
question
sql
success
error_message
row_count
chart_type
execution_time_ms
analysis
```

后续如需让用户查看历史记录，可新增：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/history` | 查询最近问数记录 |
| `GET` | `/api/history/{id}` | 查询单次问数详情 |

## 9. 前端调用方式

Streamlit 前端通过 `requests.post` 调用后端：

```python
requests.post(api_url, json={"query": query}, timeout=60)
```

默认 API 地址：

```text
http://127.0.0.1:8000/api/ask
```

可通过环境变量覆盖：

```text
AUTOBI_API_URL=http://127.0.0.1:8000/api/ask
```
