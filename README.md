# AutoBI Agent

面向汽车产业数据平台的智能问数助手。

AutoBI Agent 将分散的汽车产业 Excel 数据清洗入库到 DuckDB，并结合数据字典、指标口径、RAG 检索、Text-to-SQL、SQL 安全校验和图表推荐，让用户可以用自然语言查询汽车产销、新能源渗透率、充电设施、动力电池装车量等业务指标。

这个项目关注的不是“让大模型直接猜答案”，而是把真实数据、指标定义、查询安全和前端展示串成一条可运行、可解释、可测试的问数链路。

## 功能亮点

- **真实数据接入**：基于 `data/raw_data` 中的汽车产业 Excel 文件，覆盖品牌车型产销、新能源厂商产销、新能源总体产销、充电设施、动力电池装车量等数据主题。
- **数据资产沉淀**：将原始表清洗为统一的英文表名和字段名，并沉淀 `docs/data_dictionary.md` 与 `docs/metrics.md`，为 RAG 和 Text-to-SQL 提供稳定上下文。
- **自然语言问数**：用户输入业务问题后，系统会检索相关表结构和指标口径，生成只读 SQL，并返回查询结果。
- **SQL 安全校验**：使用 `sqlglot` 解析 SQL，只允许单条 `SELECT` 语句访问白名单表，并自动补充默认 `LIMIT`。
- **分析与可视化**：查询完成后返回 SQL、结果表、业务分析结论和图表建议，前端支持折线图、柱状图、堆叠柱状图、饼图和指标卡。
- **前后端闭环**：FastAPI 提供 `/api/ask` 问数接口，Streamlit 提供可交互页面，用户可以直接选择业务范围或输入自定义问题。
- **测试覆盖**：项目包含数据入库、RAG 检索、Text-to-SQL 服务、SQL Guard、SQL 执行器、图表推荐、分析服务、历史记录、API 和前端辅助函数测试。

## 可以回答的问题

AutoBI Agent 适合回答围绕汽车产业数据的结构化业务问题，例如：

1. 2022 年各厂商新能源汽车销量排名如何？
2. 新能源汽车渗透率的月度变化趋势如何？
3. 2022 年各车型销量 Top 5 是什么？
4. 各省充电设施数量分布如何？
5. 动力电池不同材料类型的装车量结构如何？
6. 比亚迪 2021-2022 年新能源汽车销量趋势如何？
7. 纯电动和插电式混合动力车型的销量结构有什么变化？
8. 特斯拉上海 Model3 的月度销量趋势如何？

## 系统流程

```text
原始 Excel 数据
  -> 数据清洗与字段标准化
  -> CSV 中间结果
  -> DuckDB 本地数据仓库
  -> 数据字典与指标口径
  -> RAG 检索相关上下文
  -> Text-to-SQL 生成查询语句
  -> SQL Guard 安全校验
  -> DuckDB 查询执行
  -> 图表推荐与业务分析
  -> FastAPI / Streamlit 展示
  -> 查询历史记录
```

## 核心模块

| 模块 | 说明 | 主要文件 |
| --- | --- | --- |
| 数据清洗 | 读取汽车产业 Excel，统一字段、日期、数值和长表结构 | `scripts/clean_raw_data.py` |
| DuckDB 入库 | 将清洗后的 CSV 写入本地 DuckDB 数据库 | `scripts/build_duckdb.py` |
| 数据字典 | 描述表结构、字段含义、数据源和表关系 | `docs/data_dictionary.md` |
| 指标口径 | 定义销量、产量、新能源渗透率、电池装车量等指标 | `docs/metrics.md` |
| RAG 检索 | 从数据字典和指标文档中检索问题相关上下文 | `app/services/rag_service.py` |
| Text-to-SQL | 根据用户问题和检索上下文生成 SQL | `app/services/text_to_sql_service.py` |
| SQL Guard | 校验 SQL 类型、表白名单、多语句注入和默认 LIMIT | `app/services/sql_guard.py` |
| SQL 执行 | 执行 DuckDB 查询并返回统一结果结构 | `app/services/sql_executor.py` |
| 图表推荐 | 根据字段类型和问题意图推荐可视化类型 | `app/services/chart_service.py` |
| 分析总结 | 基于查询结果生成业务分析文本 | `app/services/analysis_service.py` |
| FastAPI 接口 | 对外提供自然语言问数 API | `app/api/ask.py` |
| Streamlit 前端 | 提供可交互问数页面和业务表预览 | `frontend/streamlit_app.py` |

## 技术栈

- **后端**：FastAPI, Pydantic, Uvicorn
- **数据处理**：Pandas, OpenPyXL, xlrd
- **本地分析库**：DuckDB
- **LLM 工程**：OpenAI SDK compatible API, RAG, Text-to-SQL, Prompt Engineering
- **SQL 安全**：sqlglot
- **前端展示**：Streamlit, Altair
- **测试**：pytest

## 快速开始

### 1. 安装依赖

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置 LLM

在项目根目录创建 `.env`：

```bash
OPENAI_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=deepseek-chat
```

项目使用 OpenAI SDK compatible API，`OPENAI_BASE_URL` 和 `LLM_MODEL` 可以按实际模型服务调整。

### 3. 清洗数据

```bash
.venv/bin/python scripts/clean_raw_data.py
```

清洗结果会写入：

```text
data/cleaned/
```

### 4. 构建 DuckDB

```bash
.venv/bin/python scripts/build_duckdb.py
```

生成的本地数据库位于：

```text
data/autobi.duckdb
```

### 5. 启动后端服务

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

### 6. 启动前端页面

```bash
.venv/bin/python -m streamlit run frontend/streamlit_app.py
```

打开 Streamlit 页面后，可以选择业务范围查看数据表，也可以输入自然语言问题调用后端问数接口。

## API 示例

请求：

```bash
curl -X POST http://127.0.0.1:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "动力电池不同材料类型的装车量结构如何？"}'
```

响应会包含：

```json
{
  "query": "动力电池不同材料类型的装车量结构如何？",
  "sql": "SELECT ...",
  "result": {
    "columns": ["dimension_value", "total_capacity"],
    "rows": [["磷酸铁锂", 183.8], ["三元锂", 110.4]]
  },
  "analysis": "基于查询结果生成的业务分析结论",
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

## 项目结构

```text
AutoBI Agent/
├── app/
│   ├── api/                 # FastAPI 路由
│   ├── prompts/             # Text-to-SQL 与分析 Prompt
│   ├── services/            # RAG、SQL Guard、SQL 执行、分析、图表等服务
│   ├── main.py              # FastAPI 应用入口
│   └── schemas.py           # 请求与响应模型
├── data/
│   ├── raw_data/            # 原始汽车产业 Excel 数据
│   ├── cleaned/             # 清洗后的 CSV
│   └── autobi.duckdb        # 本地 DuckDB 数据库
├── docs/
│   ├── api_design.md        # API 设计
│   ├── data_dictionary.md   # 数据字典
│   ├── metrics.md           # 指标口径
│   ├── prompt_templates.md  # Prompt 模板
│   ├── project_summary.md   # 项目复盘
│   └── test_cases.md        # 测试用例
├── frontend/
│   └── streamlit_app.py     # Streamlit 前端
├── scripts/
│   ├── clean_raw_data.py    # 原始数据清洗
│   ├── build_duckdb.py      # DuckDB 建库
│   └── inspect_raw_data.py  # 原始数据盘点
├── tests/                   # 自动化测试
├── requirements.txt
└── README.md
```

## 测试

运行全量测试：

```bash
.venv/bin/python -m pytest -q
```

测试重点覆盖：

- 数据清洗与 DuckDB 入库结果。
- 标准业务问题的接口响应结构。
- SQL Guard 对危险 SQL、白名单外表和多语句注入的拦截。
- SQL 执行器、RAG 检索、Text-to-SQL、图表推荐和分析服务。
- Streamlit 前端辅助函数和查询历史记录。

## 文档索引

- [项目复盘](docs/project_summary.md)
- [API 设计](docs/api_design.md)
- [数据字典](docs/data_dictionary.md)
- [指标口径](docs/metrics.md)
- [Prompt 模板](docs/prompt_templates.md)
- [测试用例](docs/test_cases.md)

## 项目价值

AutoBI Agent 展示了一条从真实业务数据到 AI 问数应用的完整工程路径：先把多源 Excel 数据整理成可查询的数据资产，再通过 RAG 和 Text-to-SQL 将自然语言问题转换为安全 SQL，最后把查询结果转化为业务分析和图表展示。

对业务用户来说，它降低了查询产业指标的门槛；对数据平台开发来说，它体现了数据接入、指标规范、接口封装、SQL 安全、前端交互和自动化测试等关键工程能力。
