# AutoBI Agent Doris 数仓升级设计

本文档记录 AutoBI Agent 从本地问数原型升级为 Doris 数仓问数项目的目标设计。该设计用于指导后续实现，不代表当前代码已经全部完成。

## 1. 升级目标

当前项目已经具备真实 Excel 数据清洗、数据字典、指标口径、RAG、Text-to-SQL、SQL Guard、FastAPI 和前端展示能力。下一步不再把 PostgreSQL 作为目标数据库，而是将数据库层升级为 Apache Doris，并补齐 `ods -> dwd -> dws -> ads` 数仓分层。

升级后的项目希望体现三类能力：

- 数据开发能力：从原始 Excel 到清洗 CSV，再到 Doris 数仓分层建模。
- 数仓建模能力：通过 ODS、DWD、DWS、ADS 区分原始落库、明细标准化、汇总服务和应用指标。
- 智能问数能力：让 RAG 和 Text-to-SQL 优先面向 ADS/DWS 层生成安全 SQL，而不是直接扫原始明细表。

## 2. 本地 Doris 拓扑

本地开发阶段使用最小 Doris 集群：

```text
FastAPI
  -> Doris FE
  -> Doris BE
```

其中：

- Doris FE 负责接收 MySQL 协议连接、解析 SQL、管理元数据和调度查询。
- Doris BE 负责存储数据、扫描数据、执行聚合和返回计算结果。
- 本地只使用 `1 FE + 1 BE`，方便 Docker Compose 启动和调试。
- 简历和 README 中可以说明生产环境可扩展为多 FE、多 BE 集群，但本地演示采用单机最小集群。

未来整体链路为：

```text
Next.js / Streamlit
  -> FastAPI
  -> Doris FE
  -> Doris BE
```

## 3. 数仓分层设计

### 3.1 ODS 层

ODS 层承接 `data/cleaned` 下的清洗后 CSV，尽量保留当前清洗结果的字段结构。ODS 层主要用于追溯和后续分层加工，不直接面向问数。

建议表：

| ODS 表 | 来源 CSV | 作用 |
| --- | --- | --- |
| `ods_dim_data_source` | `dim_data_source.csv` | 保存数据源文件、主题和目标表信息 |
| `ods_vehicle_prod_sales_monthly` | `fact_vehicle_prod_sales_monthly.csv` | 保存汽车品牌车型月度产销明细 |
| `ods_nev_manufacturer_monthly` | `fact_nev_manufacturer_monthly.csv` | 保存新能源厂商月度产销明细 |
| `ods_nev_overall_monthly` | `fact_nev_overall_monthly.csv` | 保存新能源总体月度产销明细 |
| `ods_charging_infrastructure_monthly` | `fact_charging_infrastructure_monthly.csv` | 保存省份充电设施月度指标明细 |
| `ods_battery_installation_monthly` | `fact_battery_installation_monthly.csv` | 保存动力电池装车月度指标明细 |

ODS 层处理规则：

- 字段名沿用当前英文标准字段。
- `data_month` 暂可保留字符串，但进入 DWD 层时统一转为日期类型。
- 每次本地导入时允许重建 ODS 表，保证演示数据可重复初始化。

### 3.2 DWD 层

DWD 层面向标准化明细数据，修正类型、统一口径字段，并承接后续汇总计算。

建议表：

| DWD 表 | 来源 | 作用 |
| --- | --- | --- |
| `dwd_vehicle_prod_sales_monthly` | `ods_vehicle_prod_sales_monthly` | 标准化汽车品牌车型产销明细 |
| `dwd_nev_manufacturer_monthly` | `ods_nev_manufacturer_monthly` | 标准化新能源厂商产销明细 |
| `dwd_nev_overall_monthly` | `ods_nev_overall_monthly` | 标准化新能源总体产销明细 |
| `dwd_charging_infrastructure_monthly` | `ods_charging_infrastructure_monthly` | 标准化充电设施指标明细 |
| `dwd_battery_installation_monthly` | `ods_battery_installation_monthly` | 标准化动力电池装车指标明细 |

DWD 层处理规则：

- `data_month` 转为 Doris 可比较的日期类型。
- 数值指标统一为数值类型。
- 保留当前业务过滤字段，例如 `stat_type`、`vehicle_category`、`vehicle_segment`、`fuel_type`、`metric_name`、`dimension_type`。
- 不在 DWD 层做面向展示的强汇总，避免明细层混入应用指标。

### 3.3 DWS 层

DWS 层沉淀可复用的业务汇总宽表，用来服务多个 ADS 指标和问数场景。

建议表：

| DWS 表 | 作用 | 典型粒度 |
| --- | --- | --- |
| `dws_vehicle_sales_monthly` | 汇总汽车销量和产量 | 月份、厂商、车型 |
| `dws_nev_manufacturer_sales_monthly` | 汇总新能源厂商销量和产量 | 月份、厂商、能源口径 |
| `dws_nev_market_monthly` | 汇总新能源整体市场销量、产量和渗透率分子分母 | 月份 |
| `dws_charging_province_monthly` | 汇总各省充电设施指标 | 月份、省份、指标 |
| `dws_battery_structure_monthly` | 汇总动力电池材料和车型结构指标 | 月份、维度类型、维度值 |

DWS 层处理规则：

- 固化高频指标口径，例如新能源总计口径、汽车销量口径、充电设施指标口径。
- 保留足够维度，让 ADS 层可以派生排名、趋势和结构占比。
- 用作 Text-to-SQL 的主要查询层之一。

### 3.4 ADS 层

ADS 层面向前端展示和智能问数，沉淀最常问、最适合展示的应用指标表。

建议表：

| ADS 表 | 支持问题 |
| --- | --- |
| `ads_nev_manufacturer_sales_rank` | 2022 年各厂商新能源汽车销量排名如何？ |
| `ads_nev_penetration_trend` | 新能源汽车渗透率的月度变化趋势如何？ |
| `ads_vehicle_model_sales_rank` | 2022 年各车型销量 Top 5 是什么？ |
| `ads_charging_facility_province_distribution` | 各省充电设施数量分布如何？ |
| `ads_battery_material_share` | 动力电池不同材料类型的装车量结构如何？ |
| `ads_battery_vehicle_type_share` | 动力电池不同车型类别的装车量结构如何？ |

ADS 层处理规则：

- 面向前端和面试演示，优先覆盖标准问题。
- 表字段尽量贴近展示需求，例如排名、月份、指标值、占比、单位。
- Text-to-SQL 默认优先访问 ADS 层；当 ADS 无法覆盖时，再访问 DWS 层。
- SQL Guard 白名单优先开放 ADS 和 DWS 表，默认不让用户直接查询 ODS。

## 4. 数据流

目标数据流如下：

```text
data/raw_data/*.xls(x)
  -> scripts/clean_raw_data.py
  -> data/cleaned/*.csv
  -> scripts/build_doris_warehouse.py
  -> Doris ODS
  -> Doris DWD
  -> Doris DWS
  -> Doris ADS
  -> RAG / Text-to-SQL / SQL Guard
  -> SQLExecutor
  -> ChartService / AnalysisService
  -> FastAPI / Frontend
```

`scripts/clean_raw_data.py` 暂不重写。后续新增 Doris 建仓脚本，负责从 `data/cleaned` 导入 Doris，并执行分层建模 SQL。

## 5. 应用查询边界

问数链路仍保留当前服务边界：

```text
RAGService
  -> TextToSQLService
  -> SQLGuard
  -> SQLExecutor
  -> ChartService
  -> AnalysisService
  -> HistoryService
```

需要调整的边界：

- `TextToSQLService` 的 prompt 从 PostgreSQL 改为 Doris SQL。
- `SQLGuard` 的表白名单改为 ADS/DWS 表。
- `SQLExecutor` 改为通过 Doris FE 的 MySQL 协议执行查询。
- `HistoryService` 不再依赖 PostgreSQL；演示阶段可写入 Doris 的应用日志表。
- `docs/data_dictionary.md` 和 `docs/metrics.md` 需要补充 ADS/DWS 层表结构和指标口径。

## 6. 测试策略

后续实现时需要覆盖：

- Doris Compose 服务可启动，FE 和 BE 均健康。
- Doris 建仓脚本能创建 ODS、DWD、DWS、ADS 表。
- 真实 `data/cleaned` 可导入 Doris，核心表行数符合预期。
- DWS/ADS 层关键指标可查询。
- SQLExecutor 能通过 Doris FE 执行只读查询。
- SQLGuard 能拦截非只读 SQL、白名单外表和多语句注入。
- `/api/ask` 能基于 ADS/DWS 表返回标准问题结果。

测试库和演示库必须隔离，避免 pytest 重建表时覆盖本地演示数据。

## 7. 实施顺序

推荐分 4 步做：

1. 更新 Docker Compose，引入 Doris `1 FE + 1 BE`，先验证 Doris 能本地启动。
2. 新增 Doris 建仓脚本，完成 ODS、DWD、DWS、ADS 分层表创建和数据导入。
3. 改造 SQLExecutor、SQLGuard、Text-to-SQL prompt 和相关测试，切到 Doris 查询。
4. 更新数据字典、指标口径、README 和简历项目描述，突出 Doris 数仓分层和智能问数。

## 8. 暂不做

- 暂不做多 FE / 多 BE 集群。
- 暂不引入 DolphinScheduler，调度流程先用脚本表达。
- 暂不做实时写入或流式数据。
- 暂不做复杂权限系统。
- 暂不扩展到非汽车产业数据域。
