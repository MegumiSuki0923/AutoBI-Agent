# AutoBI Agent 项目复盘

本文档总结 AutoBI Agent 当前阶段的项目定位、模块设计、数据接入流程、已完成能力、测试情况和后续改进方向。

## 1. 项目定位

AutoBI Agent 是一个面向汽车产业数据平台的自然语言问数智能体。项目使用 `data/raw_data` 下的真实汽车产业 Excel 数据，完成数据盘点、字段标准化、指标口径沉淀、DuckDB 入库、RAG + Text-to-SQL、SQL 安全校验、图表推荐、结果分析和 Streamlit 前端展示。

项目目标不是做一个纯聊天机器人，而是把分散 Excel 数据整理成可查询、可解释、可测试的数据平台资产。

核心链路：

```text
原始 Excel
  -> 数据清洗
  -> CSV
  -> DuckDB
  -> 数据字典 / 指标口径
  -> RAG 检索
  -> Text-to-SQL
  -> SQL Guard
  -> SQL 执行
  -> 图表推荐
  -> 结果分析
  -> Streamlit 展示
  -> 历史记录
```

## 2. 当前能力总览

| 能力 | 对应文件 | 当前状态 |
| --- | --- | --- |
| 数据字典 | `docs/data_dictionary.md` | 已整理 |
| 指标口径 | `docs/metrics.md` | 已整理 |
| 数据清洗 | `scripts/clean_raw_data.py` | 已实现 |
| DuckDB 入库 | `scripts/build_duckdb.py` | 已实现 |
| SQL 执行 | `app/services/sql_executor.py` | 已实现 |
| RAG 检索 | `app/services/rag_service.py` | 已实现 |
| Text-to-SQL | `app/services/text_to_sql_service.py` | 已实现 |
| SQL 安全校验 | `app/services/sql_guard.py` | 已实现 |
| 分析总结 | `app/services/analysis_service.py` | 已实现 |
| 图表推荐 | `app/services/chart_service.py` | 已实现 |
| 历史记录 | `app/services/history_service.py` | 已实现 |
| FastAPI 接口 | `app/api/ask.py` | 已接入真实问数链路 |
| Streamlit 前端 | `frontend/streamlit_app.py` | 已实现 |
| 标准问题测试 | `tests/test_standard_questions.py` | 已实现 |

重要边界：当前 `/api/ask` 已串联真实 Text-to-SQL、SQL Guard、SQL Executor、ChartService、AnalysisService 和 HistoryService。自动化测试中不会真实调用外部 LLM，而是通过依赖注入替换服务。

## 3. 数据接入说明

### 3.1 原始数据目录

原始文件放在：

```text
data/raw_data/
```

MVP 使用 6 个汽车产业数据源：

| 数据源 | 主题 | 文件类型 | 目标表 |
| --- | --- | --- | --- |
| SRC001 | 汽车品牌车型产销 | `.xlsx` | `fact_vehicle_prod_sales_monthly` |
| SRC002 | 新能源汽车分厂商产销 | `.xlsx` | `fact_nev_manufacturer_monthly` |
| SRC003 | 新能源汽车总体产销 | `.xlsx` | `fact_nev_overall_monthly` |
| SRC004 | 国内充电设施数量 | `.xls` | `fact_charging_infrastructure_monthly` |
| SRC005 | 动力电池装车量分车型 | `.xls` | `fact_battery_installation_monthly` |
| SRC006 | 动力电池装车量分材料类型 | `.xls` | `fact_battery_installation_monthly` |

### 3.2 清洗流程

清洗脚本：

```bash
.venv/bin/python scripts/clean_raw_data.py
```

输出目录：

```text
data/cleaned/
```

输出 CSV：

```text
dim_data_source.csv
fact_vehicle_prod_sales_monthly.csv
fact_nev_manufacturer_monthly.csv
fact_nev_overall_monthly.csv
fact_charging_infrastructure_monthly.csv
fact_battery_installation_monthly.csv
```

清洗动作包括：

- 过滤 Excel 中的子表头行和无效行。
- 将中文原始字段映射为英文标准字段。
- 将日期统一为 `data_month`。
- 将数值列转换为数值类型。
- 按业务键去重。
- 为每张事实表生成稳定 `record_id`。
- 将充电设施和动力电池宽表转成长表结构。
- 将动力电池材料表中的 GWh / MWh 单位差异统一处理。

### 3.3 入库流程

入库脚本：

```bash
.venv/bin/python scripts/build_duckdb.py
```

目标数据库：

```text
data/autobi.duckdb
```

入库逻辑：

- 读取 `data/cleaned/*.csv`。
- 按 CSV 文件名创建同名 DuckDB 表。
- 每次执行时重新生成 `data/autobi.duckdb`。
- 返回每张表的写入行数。

### 3.4 数据访问约定

- 业务查询统一通过 DuckDB 执行。
- SQL 执行服务默认连接 `data/autobi.duckdb`。
- 执行真实用户 SQL 前必须经过 `SQLGuard`。
- 只允许访问表白名单中的业务表。
- 查询结果返回结构为 `columns + rows`，便于 FastAPI、分析服务和前端统一消费。

## 4. 模块复盘

### 4.1 Prompt 与 LLM 服务

当前项目有两类 Prompt：

- Text-to-SQL Prompt：负责从自然语言生成只读 SQL。
- Analysis Prompt：负责把查询结果总结为核心结论、数据依据和行动建议。

关键设计：

- Prompt 不直接写死全部表结构和指标口径，而是通过 RAG 注入相关上下文。
- Text-to-SQL 输出强制为 JSON，降低解析成本。
- Analysis 输出也强制为 JSON，再由服务层格式化为前端可展示文本。
- `.env` 中的 `OPENAI_BASE_URL` 和 `LLM_MODEL` 会覆盖代码默认值。

### 4.2 SQL 安全

SQL 安全是当前项目的核心工程点之一：

- 使用 `sqlglot` 解析 SQL，而不是用字符串包含判断。
- 禁止非 SELECT 操作。
- 禁止多语句注入。
- 限制表白名单。
- 禁止带 schema/catalog 前缀的表名绕过校验。
- 自动补充默认 `LIMIT 100`。

这保证了即使 LLM 生成了危险 SQL，也不会直接进入执行器。

### 4.3 图表推荐

图表推荐基于字段类型和用户意图：

- 时间字段 + 数值字段：优先折线图。
- 类别字段 + 数值字段：柱状图。
- 结构、占比、构成类问题：堆叠柱状图。
- 单行单指标：指标卡。
- 少量分类占比类结果：前端支持饼图展示。

Streamlit 前端统一使用 Altair 渲染 line、bar、stacked_bar 和 pie，并确保横坐标标签横向展示。

**优化记录**：
- 重构了字段推断中 `_is_time_field` 和 `_is_numeric_field` 识别算法。由子串检索（导致 `monthly_sales` 因为含有 `month` 而误判为时间列）升级为**分词及后缀优先级判断**。结合结果数据的真实分布做推断，彻底解决了字段误判导致表格正常渲染但无折线图/柱状图的问题。

### 4.4 历史记录

历史记录服务已实现 `query_history` 表，用于记录：

- 用户问题。
- SQL。
- 成功状态。
- 失败原因。
- 结果行数。
- 图表类型。
- 执行耗时。
- 分析结论摘要。

DuckDB `:memory:` 场景下，服务会复用同一实例内的连接，避免内存库在连接关闭后丢失表结构。

## 5. 测试复盘

当前测试覆盖：

- DuckDB 建库和表写入。
- SQL 执行器。
- RAG 检索。
- Text-to-SQL 服务。
- SQL Guard。
- 分析总结服务。
- 图表推荐服务。
- Streamlit 前端辅助函数。
- 历史记录服务。
- 标准问题、SQL 安全和边界问题。
- 混合意图路由（包含极速白名单拦截、大模型语义分类、出圈闲聊拒绝和时间轴元数据查询路径）。

当前全量测试结果：

```text
90 passed, 7 warnings
```

已知 warning：

- Pydantic V2 对 `Field(example=...)` 的弃用提示。
- 当前不影响功能，但后续可统一迁移到 `json_schema_extra`。

## 6. 当前不足

1. Text-to-SQL 和分析总结依赖外部 LLM，真实联调需要有效 `.env` 配置和稳定模型响应。
2. 前端可以展示 SQL、表格、图表和分析结论，但还没有历史记录页。
3. 数据字典和清洗脚本需要保持同步，后续字段调整时要同时更新文档和测试。
4. 当前测试偏接口契约和服务逻辑，真实业务数值回归测试还需要继续补充。
5. Pydantic V2 warning 尚未清理。

## 7. 后续建议

优先级从高到低：

1. 用真实 `.env` 配置联调标准问题，校准 Text-to-SQL 输出质量。
2. 增加真实标准问题的 SQL 和结果口径回归测试。
3. 在 Streamlit 前端增加历史记录面板或最近查询列表。
4. 修复 Pydantic V2 warning，把 `Field(example=...)` 迁移为 `json_schema_extra`。
5. 增强失败分支的用户提示，例如区分 SQL 生成失败、安全校验失败、SQL 执行失败和分析生成失败。

## 8. 项目价值总结

AutoBI Agent 当前已经具备一个企业数据问数智能体的核心骨架：

- 有真实汽车产业数据，而不是空想场景。
- 有数据字典和指标口径，能解释数据来自哪里、怎么算。
- 有 DuckDB 本地数仓，能低成本完成数据查询闭环。
- 有 RAG + Text-to-SQL 的 LLM 工程路径。
- 有 SQL Guard，能说明安全边界。
- 有分析总结和图表推荐，能从查询走到业务表达。
- 有 Streamlit 前端，能形成可演示的交互体验。
- 有标准问题测试集，能支撑持续迭代。

下一阶段最关键的是用真实 LLM 配置对标准问题做联调，持续校准生成 SQL 的字段、过滤条件和指标口径，让项目从“链路打通”推进到“稳定可演示”。 
