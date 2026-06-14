# AutoBI Agent

面向汽车产业数据的智能问数与分析系统。

AutoBI Agent 将汽车产业多源 Excel 数据清洗为标准化数据资产，写入 Apache Doris 数仓并建设 `ODS -> DWD -> DWS -> ADS` 分层，再通过 FastAPI、LangGraph、RAG、Text-to-SQL、SQL Guard 和 Next.js 前端，把自然语言问题转成安全 SQL、查询结果、图表建议和业务分析结论。

这个项目不是一个只会调用大模型的聊天 Demo，而是一条完整的本地数据应用链路：真实数据接入、数仓分层建模、指标口径沉淀、Agent 编排、安全查询、流式执行反馈、历史会话和容器化部署。

## 当前能力

- **真实汽车产业数据接入**：读取 `data/raw_data` 下的汽车产销、新能源汽车、充电设施、动力电池、全球电动车和汽车上市公司等 Excel 数据。
- **Doris 数仓分层**：通过 `scripts/build_doris_warehouse.py` 将清洗后的 CSV 导入 Doris，并生成 ODS、DWD、DWS、ADS 表。
- **指标与数据字典驱动问数**：`docs/data_dictionary.md` 和 `docs/metrics.md` 为 RAG 检索和 SQL 生成提供表结构、字段含义、指标口径和示例 SQL。
- **LangGraph Agent 编排**：后端按节点执行意图识别、表路由、上下文检索、SQL 生成、SQL 修复、安全校验、Doris 查询、图表推荐、分析总结和历史记录。
- **SQL 安全边界**：`SQLGuard` 使用 `sqlglot` 解析 SQL，只允许单条 `SELECT`，限制可访问表，并为缺少 `LIMIT` 的查询补默认限制。
- **产品化前端**：Next.js 前端提供会话列表、流式执行步骤、问答结果、SQL、结果表、ECharts 图表和分析结论。
- **统一本地入口**：Docker Compose 编排 Doris FE/BE、FastAPI、Next.js 和 Nginx，通过 Nginx 统一代理前端和 API。
- **自动化测试**：测试覆盖 API、LangGraph 问数链路、Doris 建仓脚本、SQL Guard、SQL 执行器、RAG、Text-to-SQL、图表推荐、分析服务和历史记录。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Next.js, React, TypeScript, ECharts, Framer Motion, lucide-react |
| 后端 | FastAPI, Pydantic, Uvicorn |
| Agent 编排 | LangGraph, RAG, Text-to-SQL, OpenAI-compatible API |
| 数据处理 | Pandas, OpenPyXL, xlrd |
| 数据仓库 | Apache Doris FE/BE, PyMySQL |
| SQL 安全 | sqlglot |
| 部署 | Docker Compose, Nginx |
| 测试 | pytest |

## 系统流程

```text
data/raw_data/*.xls(x)
  -> scripts/clean_raw_data.py
  -> data/cleaned/*.csv
  -> scripts/build_doris_warehouse.py
  -> Doris ODS / DWD / DWS / ADS
  -> 数据字典与指标口径
  -> LangGraph Agent
     -> 意图识别
     -> 表路由
     -> RAG 检索
     -> Text-to-SQL
     -> SQL 修复
     -> SQL Guard
     -> Doris 查询
     -> 图表推荐
     -> 分析总结
     -> 历史记录
  -> FastAPI / SSE
  -> Next.js / ECharts / Nginx
```

## 数仓分层

| 层级 | 作用 | 典型表 |
| --- | --- | --- |
| ODS | 清洗后数据原样落库，保留可追溯明细 | `ods_fact_vehicle_prod_sales_monthly`, `ods_fact_nev_manufacturer_monthly` |
| DWD | 明细标准化，统一日期、数值和业务字段 | `dwd_vehicle_prod_sales_monthly`, `dwd_nev_overall_monthly` |
| DWS | 面向多场景复用的汇总服务层 | `dws_vehicle_sales_monthly`, `dws_nev_market_monthly`, `dws_battery_structure_monthly` |
| ADS | 面向前端展示和标准问题的应用层 | `ads_nev_manufacturer_sales_rank`, `ads_nev_penetration_trend`, `ads_battery_material_share` |

默认问数策略是优先查询 ADS 层；ADS 无法覆盖时查询 DWS/DWD 层；SQL Guard 通过白名单约束模型生成 SQL 的可访问范围。

## 可以展示的问题

1. 2022 年各厂商新能源汽车销量排名如何？
2. 2022 年新能源汽车渗透率的月度趋势如何？
3. 2022 年哪些车型销量最高？
4. 比亚迪 2021-2022 年新能源汽车销量趋势如何？
5. 特斯拉上海 Model3 的月度销量趋势如何？
6. 哪些省份的充电设施数量增长最快？
7. 不同材料类型动力电池装车量占比如何变化？
8. 不同车型类别的动力电池装车量趋势如何？

## 项目结构

```text
AutoBI Agent/
├── app/
│   ├── api/                 # FastAPI 路由：问数、流式问数、历史会话
│   ├── graphs/              # LangGraph 问数编排
│   ├── prompts/             # Text-to-SQL、表路由、分析 Prompt
│   ├── services/            # RAG、SQL Guard、Doris 查询、图表、分析、历史记录
│   ├── main.py              # FastAPI 应用入口
│   └── schemas.py           # API 请求与响应模型
├── data/
│   ├── raw_data/            # 原始汽车产业 Excel 和产业图谱素材
│   └── cleaned/             # 清洗后的 CSV 数据资产
├── docs/
│   ├── api_design.md        # API 设计
│   ├── data_dictionary.md   # Doris 表结构与问数边界
│   ├── doris_warehouse_design.md
│   ├── metrics.md           # 指标口径和示例 SQL
│   ├── project_summary.md
│   └── test_cases.md
├── frontend-next/           # Next.js + TypeScript 前端
├── frontend/                # Streamlit 调试页面
├── nginx/
│   └── default.conf         # 前端和 API 反向代理
├── scripts/
│   ├── clean_raw_data.py
│   ├── build_doris_warehouse.py
│   ├── clean_new_facts.py
│   └── generate_dimensions.py
├── tests/
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 配置 Python 环境

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置 LLM

在项目根目录创建或更新 `.env`：

```bash
OPENAI_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=deepseek-chat
```

项目使用 OpenAI-compatible API，`OPENAI_BASE_URL` 和 `LLM_MODEL` 可以按实际模型服务调整。

### 3. 清洗原始数据

```bash
.venv/bin/python scripts/clean_raw_data.py
```

清洗结果写入 `data/cleaned/`。

### 4. 启动完整本地链路

```bash
docker-compose up --build
```

启动后可访问：

| 服务 | 地址 |
| --- | --- |
| Nginx 统一入口 | `http://127.0.0.1/` |
| FastAPI Swagger | `http://127.0.0.1:8000/docs` |
| Doris FE HTTP | `http://127.0.0.1:8030/` |
| Doris FE MySQL 协议 | `127.0.0.1:9030` |

如果本机 Docker 内存较小，Doris FE/BE 可能启动较慢；建议给 Docker/Colima 预留至少 6GB 内存。

### 5. 构建 Doris 数仓

Doris 容器启动并健康后执行：

```bash
.venv/bin/python scripts/build_doris_warehouse.py
```

默认连接配置：

```text
DORIS_HOST=127.0.0.1
DORIS_QUERY_PORT=9030
DORIS_USER=root
DORIS_PASSWORD=
DORIS_DATABASE=autobi
```

### 6. 单独启动后端

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 7. 单独启动 Next.js 前端

```bash
cd frontend-next
npm install
npm run dev
```

开发模式默认访问 `http://127.0.0.1:3000/`。完整容器化演示优先使用 Nginx 入口 `http://127.0.0.1/`。

## API 示例

普通问数接口：

```bash
curl -X POST http://127.0.0.1:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "2022 年各厂商新能源汽车销量排名如何？"}'
```

流式问数接口：

```bash
curl -N -X POST http://127.0.0.1:8000/api/ask/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "不同材料类型动力电池装车量占比如何变化？", "thread_id": "demo-session"}'
```

响应结构会包含：

```json
{
  "query": "2022 年各厂商新能源汽车销量排名如何？",
  "sql": "SELECT manufacturer_name, total_sales_units, sales_rank FROM ads_nev_manufacturer_sales_rank WHERE stat_year = 2022 ORDER BY sales_rank LIMIT 100",
  "result": {
    "columns": ["manufacturer_name", "total_sales_units", "sales_rank"],
    "rows": [["比亚迪", 1860000, 1]]
  },
  "analysis": "基于查询结果生成的业务分析结论",
  "chart_suggestion": {
    "chart_type": "bar",
    "x_axis": "manufacturer_name",
    "y_axes": ["total_sales_units"],
    "title": "2022 年新能源汽车厂商销量排名"
  },
  "success": true,
  "error_message": null,
  "execution_time_ms": 120.5,
  "execution_steps": [
    {
      "name": "generate_sql",
      "status": "success",
      "message": "已生成候选 SQL",
      "elapsed_ms": 24.18
    }
  ]
}
```

## 测试

运行全量测试：

```bash
.venv/bin/python -m pytest -q
```

测试重点：

- Doris 建仓 SQL 和分层表生成逻辑。
- LangGraph 问数链路的成功、失败、日常问答和 SQL 拦截路径。
- SQL Guard 对危险 SQL、多语句、非白名单表和默认 `LIMIT` 的处理。
- SQLExecutor、HistoryService、RAGService、TextToSQLService、ChartService、AnalysisService。
- 标准问题的 SQL 生成和 API 响应结构。

## 核心文件索引

| 文件 | 说明 |
| --- | --- |
| `app/graphs/ask_graph.py` | LangGraph 问数状态机 |
| `app/services/ask_service.py` | FastAPI 到 LangGraph 的应用服务入口 |
| `app/services/sql_guard.py` | SQL 安全校验与改写 |
| `app/services/sql_executor.py` | Doris FE MySQL 协议查询执行器 |
| `app/services/history_service.py` | Doris 中的查询历史和会话记录 |
| `scripts/clean_raw_data.py` | 原始 Excel 清洗 |
| `scripts/build_doris_warehouse.py` | Doris ODS/DWD/DWS/ADS 建仓 |
| `frontend-next/src/app/page.tsx` | Next.js 问数页面 |
| `frontend-next/src/components/Charts.tsx` | ECharts 图表渲染 |
| `frontend-next/src/components/ExecutionSteps.tsx` | Agent 执行步骤展示 |
| `nginx/default.conf` | 前端和 API 统一代理 |

## 文档索引

- [API 设计](docs/api_design.md)
- [Doris 数仓设计](docs/doris_warehouse_design.md)
- [数据字典](docs/data_dictionary.md)
- [指标口径](docs/metrics.md)
- [Prompt 模板](docs/prompt_templates.md)
- [测试用例](docs/test_cases.md)
- [项目复盘](docs/project_summary.md)

## 项目价值

AutoBI Agent 展示的是“数据工程 + 数仓建模 + AI Agent + BI 展示”的组合能力：底层用真实产业数据和 Doris 分层承接指标口径，上层用 LangGraph 和 Text-to-SQL 将业务问题转为可解释、可审计、可限制的查询，再通过 Next.js 前端把执行过程、SQL、表格、图表和分析结论展示出来。

对业务用户来说，它降低了查询汽车产业指标的门槛；对工程展示来说，它覆盖了数据清洗、数仓建模、后端 API、Agent 编排、安全边界、前端交互、容器化和自动化测试等一套完整项目能力。
