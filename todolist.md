# AutoBI Agent Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前 Streamlit + DuckDB 的本地问数原型升级为更适合简历展示的 Next.js + FastAPI + LangGraph + Apache Doris 数仓 + Docker + Nginx 项目。

**Architecture:** 保留现有 FastAPI 问数接口和 SQL 安全边界，先把本地环境稳定跑通，再把数据库层升级为 Doris 数仓，并补齐 `ods -> dwd -> dws -> ads` 分层。Next.js 只负责产品化界面，FastAPI 负责 LangGraph 问数流程、SQL Guard、Doris 访问和分析结果返回。

**Tech Stack:** Next.js, TypeScript, FastAPI, LangGraph, Apache Doris, Docker Compose, Nginx, RAG, Text-to-SQL, SQL Guard, ECharts/Recharts, pytest.

---

## 当前状态

- 当前前端：`frontend/streamlit_app.py`
- 当前后端：`app/main.py`, `app/api/ask.py`
- 当前问数流程：`RAGService -> TextToSQLService -> SQLGuard -> SQLExecutor -> ChartService -> AnalysisService`
- 当前数据库：原型阶段为 `data/autobi.duckdb`；PostgreSQL 迁移已完成但按 Lain 最新决策废弃；目标数据库改为 Docker Compose 中的 Apache Doris。
- 当前数据来源：`data/raw_data` 下的汽车产业 Excel 文件
- 当前测试：`tests/` 下已有 API、RAG、Text-to-SQL、SQL Guard、SQL 执行、图表、分析、前端辅助函数测试
- 当前目标数仓设计：见 `docs/doris_warehouse_design.md`

## Phase 0: 先确认本地旧版本能跑

本阶段按 Lain 的要求跳过，不计入本次完成状态。

- [ ] 建立或修复 Python 虚拟环境。
- [ ] 安装当前依赖：`pip install -r requirements.txt`
- [ ] 执行数据清洗：`python scripts/clean_raw_data.py`
- [ ] 构建当前 DuckDB：`python scripts/build_duckdb.py`
- [ ] 跑测试：`pytest -q`
- [ ] 启动 FastAPI：`uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- [ ] 启动 Streamlit：`streamlit run frontend/streamlit_app.py`
- [ ] 用 3 个标准问题手动验证接口、SQL、表格、图表和分析结论。

## Phase 1: 引入 Docker Compose，但先不改业务逻辑

- [x] 新增 `Dockerfile.backend`，用于运行 FastAPI。
- [x] 新增 `docker-compose.yml`，先只编排 `backend` 服务。
- [x] 新增 `.dockerignore`，排除 `.venv`、缓存、测试产物和本地数据库临时文件。
- [x] 用 Docker 启动当前 FastAPI，确认 `/docs` 和 `/api/ask` 可访问。
- [x] 保持 Streamlit 暂时在本机运行，只调用 Docker 内的 FastAPI。

完成记录：

- [x] 已安装并启动本地 Docker 运行环境：Docker CLI + Docker Compose + Colima。
- [x] 已构建后端镜像：`docker-compose build backend`。
- [x] 已启动后端容器：`docker-compose up -d backend`。
- [x] 已验证根路径：`GET http://127.0.0.1:8000/` 返回 `status=online`。
- [x] 已验证问数接口：`POST http://127.0.0.1:8000/api/ask` 对 `你好` 返回正常 JSON。

## Phase 2A: PostgreSQL 迁移探索记录（已废弃）

本阶段曾经用于验证“从 DuckDB 迁移到 PostgreSQL”的可行性，已完成本地 Docker Compose、入库、查询和测试验证。但 Lain 最新决策是不使用 PostgreSQL，改用 Apache Doris 建设更像数仓项目的 `ods -> dwd -> dws -> ads` 分层。因此本阶段只作为历史探索记录，不再作为后续目标架构。

- [x] 在 `docker-compose.yml` 中加入 `postgres` 服务。
- [x] 新增数据库连接配置，例如 `DATABASE_URL`。
- [x] 新增 PostgreSQL 初始化脚本，把当前 DuckDB 表结构迁移为 PostgreSQL 表结构。
- [x] 修改数据入库脚本，将清洗后的 CSV 写入 PostgreSQL。
- [x] 修改 `SQLExecutor`，从 DuckDB 查询改为 PostgreSQL 查询。
- [x] 修改 `SQLGuard` 的 SQL 方言和白名单校验，确保仍只允许安全的只读查询。
- [x] 更新相关测试：数据入库、SQL 执行、SQL Guard、API。
- [x] 本地验证：通过 Docker Compose 启动 PostgreSQL + FastAPI，跑通 `/api/ask`。

完成记录：

- [x] 已新增 `postgres` Compose 服务，包含健康检查、数据卷和本地 `5432` 端口映射。
- [x] 已为 `backend` 配置 `DATABASE_URL` 和 `TEST_DATABASE_URL`，并等待 PostgreSQL healthy 后再启动。
- [x] 已将测试库隔离到 `autobi_test`，避免 pytest 重建表时覆盖本地演示库 `autobi`。
- [x] 已新增 `scripts/build_postgres.py`，从 `data/cleaned` 重建并导入 PostgreSQL 分析表。
- [x] 已导入真实清洗数据：6 张表，共 85318 行。
- [x] 已将 `SQLExecutor` 和 `HistoryService` 切换为 PostgreSQL 连接。
- [x] 已将 `SQLGuard` 默认方言切换为 `postgres`，并保留只读查询、白名单表和自动 `LIMIT` 校验。
- [x] 已更新 Text-to-SQL prompt 和 API 文案中的数据库目标为 PostgreSQL。
- [x] 已通过 Phase 2 相关测试：`26 passed`。
- [x] 已通过 API 和标准问题测试：`28 passed`。
- [x] 已通过全量测试：`89 passed`。
- [x] 已验证 Docker 本地接口：`GET /` 返回 `status=online`，`POST /api/ask` 对 `你好` 返回正常 JSON。
- [x] 已验证真实 PostgreSQL 查询：新能源厂商销量汇总可返回比亚迪、特斯拉等结果。

## Phase 2B: 迁移到 Apache Doris 数仓

目标设计见 `docs/doris_warehouse_design.md`。本阶段要把数据库目标从 PostgreSQL 改为 Doris，并把当前 6 张分析表升级为数仓分层模型。

- [x] 调整 `docker-compose.yml`，用 Doris `1 FE + 1 BE` 替换 PostgreSQL。
- [x] 新增 Doris 连接配置，例如 `DORIS_HOST`、`DORIS_QUERY_PORT`、`DORIS_USER`、`DORIS_PASSWORD`、`DORIS_DATABASE`。
- [x] 新增 Doris 建仓脚本，例如 `scripts/build_doris_warehouse.py`。
- [x] 建设 ODS 层：从 `data/cleaned/*.csv` 导入 Doris ODS 表。
- [x] 建设 DWD 层：统一日期、数值类型和明细口径。
- [x] 建设 DWS 层：沉淀月度销量、厂商销量、市场趋势、充电设施、电池结构等汇总表。
- [x] 建设 ADS 层：沉淀标准问题所需的排名、趋势、分布、占比类应用表。
- [x] 修改 `SQLExecutor`，通过 Doris FE 的 MySQL 协议执行只读查询。
- [x] 修改 `HistoryService`，去掉 PostgreSQL 依赖，演示阶段写入 Doris 应用日志表。
- [x] 修改 `SQLGuard`，默认面向 Doris SQL，并将白名单切换到 ADS/DWS 表。
- [x] 修改 Text-to-SQL prompt，让模型优先查询 ADS 层，其次查询 DWS 层，默认不直接查询 ODS。
- [x] 更新 `docs/data_dictionary.md`，补充 Doris ODS/DWD/DWS/ADS 表结构。
- [x] 更新 `docs/metrics.md`，补充 ADS/DWS 指标口径和示例 SQL。
- [x] 更新测试：Doris 建仓、SQL 执行、SQL Guard、API、标准问题。
- [x] 本地验证：通过 Docker Compose 启动 Doris + FastAPI，跑通 `/api/ask`。

## Phase 3: 用 LangGraph 替换 AskPipeline 的显式编排

- [x] 新增 `app/graphs/ask_graph.py`，定义问数图。
- [x] 将当前流程拆成 LangGraph 节点：意图判断、RAG 检索、SQL 生成、SQL 安全校验、SQL 执行、图表推荐、分析总结、历史记录。
- [x] 保留现有 `RAGService`、`TextToSQLService`、`SQLGuard`、`SQLExecutor`、`ChartService`、`AnalysisService` 的服务边界。
- [x] 修改 `app/api/ask.py`，让 `/api/ask` 调用 LangGraph，而不是直接调用旧 `AskPipeline.run()`。
- [x] 为 LangGraph 节点补测试，确保成功路径、非数据问题、SQL 拦截和失败记录都能覆盖。
- [x] 在 API 响应里增加可展示的执行步骤，供前端展示 Agent 运行链路。

完成记录：

- [x] 已采用 `AskService -> AskGraph -> 现有服务` 的结构，避免继续保留旧 `AskPipeline` 作为兼容外壳。
- [x] 已新增 `app/graphs/ask_graph.py`（525 行），使用 `langgraph.graph.StateGraph` 定义 11 个节点：`intent_check`、`daily_qa`、`retrieve_context`、`generate_sql`、`guard_sql`、`execute_sql`、`recommend_chart`、`generate_analysis`、`record_success`、`record_failure`、`build_response`。
- [x] 已新增 `app/services/ask_service.py`（71 行），作为 HTTP 入口到 LangGraph 的桥接层。
- [x] 已修改 `app/api/ask.py`，`/api/ask` 通过 `AskService -> AskGraph.run()` 调用 LangGraph，旧 `AskPipeline` 已完全移除。
- [x] 已新增 `ExecutionStep` Pydantic 模型（`name`、`status`、`message`、`elapsed_ms`），`AskResponse` 增加 `execution_steps` 字段。
- [x] 已实现条件路由：`intent_check` 根据 `is_data_query` 分支到 `daily_qa` 或 `retrieve_context`；`generate_sql` 后根据 LLM 判定分支到 `guard_sql` 或 `record_success`；所有节点异常自动路由到 `record_failure`。
- [x] 已保留 7 个现有服务边界（RAGService、TextToSQLService、SQLGuard、SQLExecutor、ChartService、AnalysisService、HistoryService），通过依赖注入到 AskGraph。
- [x] 已在 `tests/test_ask_api.py`（376 行，8 个测试）覆盖成功问数（完整 9 步链路）、日常/能力说明问题、LLM 判定非数据问题、SQL Guard 拦截、失败历史记录路径和 LLM 服务不初始化验证。

## Phase 4: 新建 Next.js 前端替换 Streamlit 展示层

- [x] 新增 `frontend-next/`。
- [x] 使用 Next.js + TypeScript 建立前端项目。
- [x] 设计首页布局：数据主题、推荐问题、问数输入框、最近查询。
- [x] 设计结果区：SQL 展示、结果表格、图表、分析结论、执行耗时。
- [x] 设计 LangGraph 执行步骤区：展示 RAG、SQL 生成、安全校验、执行、分析等节点状态。
- [x] 接入 `/api/ask`。
- [x] 使用 ECharts 或 Recharts 渲染折线图、柱状图、堆叠柱状图、饼图和指标卡。
- [x] 保留 Streamlit 为旧版调试页面，或在升级完成后删除。

## Phase 5: 加入 Nginx 本地反向代理

- [x] 新增 `nginx/default.conf`。
- [x] 让 `/` 转发到 Next.js 前端。
- [x] 让 `/api/` 转发到 FastAPI 后端。
- [x] 在 `docker-compose.yml` 中加入 `nginx` 服务。
- [x] 本地验证统一入口，例如 `http://127.0.0.1` 可以访问前端，前端能正常调用 `/api/ask`。

## Phase 6: 展示效果和简历材料收尾

- [ ] 更新 `README.md`，把技术栈改为 Next.js + FastAPI + LangGraph + Apache Doris + Docker Compose + Nginx。
- [ ] 更新系统流程图，突出 LangGraph 编排、SQL Guard、Doris 数仓分层、可视化前端。
- [ ] 增加本地 Docker 启动说明。
- [ ] 增加 5-8 个适合面试展示的标准问题。
- [ ] 增加截图或演示说明：问数页面、SQL 结果、图表、LangGraph 执行链路。
- [ ] 更新简历项目描述，突出“产品化前端 + Agent 编排 + Doris 数仓分层 + 容器化部署”。

## 优先级建议

1. 先跑通当前旧版本，确认没有历史环境问题。
2. 再做 Docker Compose，因为它是后面 Doris、Next.js、Nginx 的本地底座。
3. 先迁 Doris 数仓，再接 LangGraph，避免同时排查数据库和编排层问题。
4. 最后做 Next.js 和 Nginx，因为它们主要影响展示效果。

## 暂不做

- [ ] 暂不本地部署大模型，LLM 继续走外部 OpenAI-compatible API。
- [ ] 暂不做多用户权限系统，简历展示阶段先保留单用户问数体验。
- [ ] 暂不做复杂 BI 拖拽配置，优先自然语言问数、SQL、图表和执行链路展示。
- [ ] 暂不做云服务器部署，先保证本地 Docker Compose 全链路可运行。
