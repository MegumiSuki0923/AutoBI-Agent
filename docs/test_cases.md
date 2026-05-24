# AutoBI Agent 测试用例集

本文档记录 Day 13 的标准问数测试、SQL 安全测试和边界问题测试。当前 `/api/ask` 已接入真实问数链路；自动化测试通过依赖覆盖替代外部 LLM，重点验证接口契约、链路编排、SQL 安全边界和异常输入处理。

## 1. 标准问数测试

测试文件：`tests/test_standard_questions.py`

目标：确保前端暴露的标准问题都可以被 `/api/ask` 正常处理，并返回完整的问数结果。

| 编号 | 测试问题 | 预期结果 |
|---|---|---|
| SQ-001 | 2022 年各厂商新能源汽车销量排名如何？ | 接口返回 200，`success=true`，包含 SQL、结果表、分析结论、图表建议和执行耗时 |
| SQ-002 | 新能源汽车渗透率的月度变化趋势如何？ | 接口返回 200，响应结构完整 |
| SQ-003 | 各省充电设施数量分布如何？ | 接口返回 200，图表类型为 `bar` |
| SQ-004 | 动力电池不同材料类型的装车量结构如何？ | 接口返回 200，图表类型为 `pie` |
| SQ-005 | 2022 年各车型销量 Top 5 是什么？ | 接口返回 200，响应结构完整 |

关键断言：

- `query` 与用户输入保持一致。
- `sql` 非空。
- `result.columns` 和 `result.rows` 非空。
- `analysis` 非空。
- `chart_suggestion.chart_type` 属于 `metric`、`line`、`bar`、`stacked_bar`、`pie`。
- `execution_time_ms >= 0`。

## 2. SQL 安全测试

测试文件：`tests/test_standard_questions.py`

目标：确保标准问数链路中可能生成的 SQL 必须通过 `SQLGuard` 校验；危险 SQL 必须被拒绝。

### 2.1 合法 SQL

| 编号 | SQL 类型 | 预期结果 |
|---|---|---|
| SG-001 | 厂商销量聚合查询 | 通过校验，自动补充 `LIMIT 100` |
| SG-002 | 新能源渗透率趋势查询，已有 `LIMIT 12` | 通过校验，保留原有 LIMIT |
| SG-003 | 动力电池装车量 CTE 查询 | 通过校验，允许 CTE 别名并自动补充 LIMIT |

### 2.2 危险 SQL

| 编号 | SQL 类型 | 预期结果 |
|---|---|---|
| SG-101 | `DROP TABLE` | 抛出 `SQLGuardError` |
| SG-102 | `DELETE FROM` | 抛出 `SQLGuardError` |
| SG-103 | 查询白名单外表 `user_credentials` | 抛出 `SQLGuardError` |
| SG-104 | 多语句注入：`SELECT ...; DROP TABLE ...` | 抛出 `SQLGuardError` |
| SG-105 | `COPY ... TO` 导出数据 | 抛出 `SQLGuardError` |

## 3. 边界问题测试

测试文件：`tests/test_standard_questions.py`

目标：确认接口在非理想输入下不会崩溃，并对明显无效请求返回清晰结果。

| 编号 | 输入 | 预期结果 |
|---|---|---|
| BQ-001 | 请求体缺少 `query` 字段 | FastAPI/Pydantic 返回 422 |
| BQ-002 | 业务外问题：`请分析明天上海天气对销量的影响` | 通过测试替身验证接口不崩溃；真实链路中应由 Text-to-SQL 或分析服务返回可解释失败 |
| BQ-003 | 超长问题文本 | 接口返回 200，不崩溃，`query` 原样回传 |

## 4. 后续扩展建议

当前测试集先覆盖稳定的接口契约和安全边界。进入真实 Text-to-SQL 链路后，建议继续补充：

- 标准问题到具体 SQL 模板或字段集合的断言。
- SQL 执行结果的行数、字段名和指标口径断言。
- 空结果集、无匹配表、LLM 生成非法 SQL 时的历史记录落库断言。
- 前端 Streamlit 对标准问题一键查询的端到端测试。
