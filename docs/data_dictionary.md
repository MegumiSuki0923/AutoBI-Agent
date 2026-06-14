# AutoBI Agent 数据字典

## 1. 文档目的

本文档定义 AutoBI Agent Doris 数仓阶段使用的汽车产业数据表。原始数据来自 `data/raw_data` 下的多源 Excel 文件，先清洗为 `data/cleaned` CSV，再由 `scripts/build_doris_warehouse.py` 写入 Doris，并形成 `ODS -> DWD -> DWS -> ADS` 分层。

```text
data/raw_data/*.xls(x)
  -> data/cleaned/*.csv
  -> Doris ODS
  -> Doris DWD
  -> Doris DWS
  -> Doris ADS
```

数据字典的作用：

- 记录原始数据源、ODS 落库表和 ADS/DWS 查询表。
- 明确字段名称、Doris 类型、业务含义和示例值。
- 为 RAG 检索和 Text-to-SQL 生成提供表结构上下文。
- 为 SQL 安全校验提供表白名单和字段白名单。

## 2. 数据范围

MVP 阶段聚焦汽车产业多源数据问数，不再使用营销漏斗场景。核心数据域包括：

- 汽车品牌 / 车型产销数据。
- 新能源汽车厂商产销数据。
- 新能源汽车总体产销数据。
- 充电设施数据。
- 动力电池装车量数据。

当前不覆盖：

- 销售线索。
- 试驾预约。
- 广告投放。
- CPL 单线索成本。
- 客户个人信息。

## 3. 原始数据源

| 数据源 ID | 原始文件 | 数据主题 | 时间粒度 | MVP 用途 |
| --- | --- | --- | --- | --- |
| `SRC001` | `1汽车分品牌产销(95家车企，768个车型，201512-202210月度数据).xlsx` | 汽车品牌 / 车型产销 | 月 | 厂商销量、车型销量、产销趋势、总汽车销量分母 |
| `SRC002` | `2新能源汽车分厂商产销(207家厂商，201812-202210月度数据).xlsx` | 新能源汽车分厂商产销 | 月 | 新能源厂商销量排名、厂商趋势 |
| `SRC003` | `3新能源汽车总体产销(201812-202210月度数据).xlsx` | 新能源汽车总体产销 | 月 | 新能源总量、燃料类型结构、新能源渗透率分子 |
| `SRC004` | `10国内充电设施数量（省份，月，201602-202302）.xls` | 国内充电设施数量 | 月 | 省份充电设施趋势和区域对比 |
| `SRC005` | `16动力电池装车量分车型（月，201909-202301，10个指标）.xls` | 动力电池装车量分车型 | 月 | 不同车型类别电池装车量趋势 |
| `SRC006` | `17动力电池装车量分材料类型（月，201701-202301，10个指标）.xls` | 动力电池装车量分材料类型 | 月 | 材料类型占比和装车量趋势 |

说明：

- `.xlsx` 文件可优先用 `openpyxl` 或 pandas 读取。
- `.xls` 文件需要在 Day3 数据接入时确认读取依赖，建议使用 `xlrd` 或转换为 `.xlsx` 后再入库。
- 所有清洗结果统一使用英文表名和英文字段名，中文业务含义保存在本文档中。

## 4. 表清单

| 表名 | 中文名 | 表类型 | 来源 | 作用 |
| --- | --- | --- | --- | --- |
| `ods_dim_data_source` | 数据源 ODS 表 | ODS | 文件清单 | 记录原始文件、主题、粒度和入库状态 |
| `dim_time` | 时间维表 | DIM | - | 包含年、季度、月等时间维度 |
| `dim_manufacturer` | 厂商维表 | DIM | - | 包含厂商名称、品牌集团、国别 |
| `dim_vehicle_model` | 车型维表 | DIM | - | 包含车型名称、车型大类、燃料类型 |
| `dim_province` | 省份/地区维表 | DIM | - | 包含省份、大区、等级 |
| `dim_fuel_type` | 燃料类型维表 | DIM | - | 包含燃料分类信息 |
| `dim_battery_material` | 电池材料维表 | DIM | - | 包含材料分类 |
| `dim_charging_operator` | 充电桩运营商维表 | DIM | - | 包含运营商分类 |
| `ods_ods_fact_vehicle_prod_sales_monthly` | 汽车品牌车型 ODS 表 | ODS | `SRC001` | 保留汽车品牌车型月度产销清洗结果 |
| `ods_ods_fact_nev_manufacturer_monthly` | 新能源厂商 ODS 表 | ODS | `SRC002` | 保留新能源厂商月度产销清洗结果 |
| `ods_ods_fact_nev_overall_monthly` | 新能源总体 ODS 表 | ODS | `SRC003` | 保留新能源总体月度产销清洗结果 |
| `ods_ods_fact_charging_infrastructure_monthly` | 充电设施 ODS 表 | ODS | `SRC004` | 保留省份充电设施月度指标 |
| `ods_ods_fact_battery_installation_monthly` | 动力电池 ODS 表 | ODS | `SRC005`, `SRC006` | 保留电池装车量、材料类型和车型类别指标 |
| `dwd_global_ev_sales_yearly` | 全球电动汽车年度销量表 | DWD | - | 国家/地区年度纯电动和插混销量 |
| `dwd_global_ev_stock_yearly` | 全球电动汽车年度保有量表 | DWD | - | 国家/地区年度保有量 |
| `dwd_battery_production_monthly` | 动力电池月度产量表 | DWD | - | 各材料类型动力电池月度产量 |
| `dwd_vehicle_production_province_monthly` | 汽车分省月度产量表 | DWD | - | 各省份所有汽车月度产量 |
| `dwd_charging_operator_monthly` | 充电桩运营商月度电量表 | DWD | - | 各运营商月度充电量 |
| `dws_vehicle_sales_monthly` | 汽车车型月度销量汇总表 | DWS | DWD 汽车明细 | 服务车型销量和产销对比 |
| `dws_nev_manufacturer_sales_monthly` | 新能源厂商月度销量汇总表 | DWS | DWD 厂商明细 | 服务厂商销量排名和趋势 |
| `dws_nev_market_monthly` | 新能源市场月度汇总表 | DWS | DWD 新能源总体明细 | 服务新能源总量和渗透率趋势 |
| `dws_charging_province_monthly` | 省份充电设施月度汇总表 | DWS | DWD 充电设施明细 | 服务省份分布和趋势 |
| `dws_battery_structure_monthly` | 动力电池结构月度汇总表 | DWS | DWD 电池明细 | 服务材料和车型类别结构 |
| `ads_nev_manufacturer_sales_rank` | 新能源厂商销量排名表 | ADS | DWS 厂商销量 | 标准问题：年度厂商新能源销量排名 |
| `ads_nev_penetration_trend` | 新能源渗透率趋势表 | ADS | DWS 新能源市场 | 标准问题：新能源渗透率月度趋势 |
| `ads_vehicle_model_sales_rank` | 车型销量排名表 | ADS | DWS 车型销量 | 标准问题：年度车型销量 Top N |
| `ads_charging_facility_province_distribution` | 充电设施省份分布表 | ADS | DWS 充电设施 | 标准问题：省份充电设施分布 |
| `ads_battery_material_share` | 动力电池材料占比表 | ADS | DWS 电池结构 | 标准问题：材料类型装车量结构 |
| `ads_battery_vehicle_type_share` | 动力电池车型占比表 | ADS | DWS 电池结构 | 标准问题：车型类别装车量结构 |

## 5. 表关系

```text
data/cleaned/*.csv
  -> ods_* 原始落库层
  -> dwd_* 明细标准化层
  -> dws_* 汇总服务层
  -> ads_* 应用问数层
```

业务关联说明：

- 各层通过 `data_month` 对齐月度时间粒度。
- ODS 层保留 CSV 字段，DWD 层统一日期和数值类型，DWS 层沉淀可复用汇总，ADS 层面向标准问题。
- Text-to-SQL 默认优先查询 ADS；ADS 覆盖不了时查询 DWS；默认不直接查询 ODS/DWD。
- 新能源渗透率优先使用 `ads_nev_penetration_trend`；如果需要重新计算，必须在 DWS 层按 `data_month` 对齐分子和分母。

## 6. 表结构设计

### 6.0 Doris 问数层表结构速查

Text-to-SQL 默认优先使用以下 ADS/DWS 表：

| 表名 | 字段 |
| --- | --- |
| `ads_nev_manufacturer_sales_rank` | `stat_year`, `manufacturer_name`, `total_sales_units`, `sales_rank` |
| `ads_vehicle_model_sales_rank` | `stat_year`, `manufacturer_name`, `model_name`, `total_sales_units`, `sales_rank` |
| `ads_nev_penetration_trend` | `data_month`, `nev_sales_units`, `total_vehicle_sales_units`, `penetration_rate` |
| `ads_charging_facility_province_distribution` | `data_month`, `province`, `metric_name`, `metric_value`, `unit` |
| `ads_battery_material_share` | `data_month`, `material_type`, `metric_name`, `metric_value`, `share`, `unit` |
| `ads_battery_vehicle_type_share` | `data_month`, `vehicle_type`, `metric_name`, `metric_value`, `share`, `unit` |
| `dws_vehicle_sales_monthly` | `data_month`, `manufacturer_name`, `model_name`, `sales_units`, `production_units` |
| `dws_nev_manufacturer_sales_monthly` | `data_month`, `manufacturer_name`, `sales_units`, `production_units` |
| `dws_nev_market_monthly` | `data_month`, `sales_units`, `production_units` |
| `dws_charging_province_monthly` | `data_month`, `province`, `metric_name`, `metric_value`, `unit` |
| `dws_battery_structure_monthly` | `data_month`, `dimension_type`, `dimension_value`, `metric_name`, `metric_value`, `unit` |

### 6.1 `dim_data_source` 数据源维表

| 字段名 | Doris 类型 | 是否主键 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `source_id` | `VARCHAR` | 是 | 否 | 数据源 ID | `SRC001` |
| `file_name` | `VARCHAR` | 否 | 否 | 原始文件名 | `1汽车分品牌产销...xlsx` |
| `topic` | `VARCHAR` | 否 | 否 | 数据主题 | `汽车品牌车型产销` |
| `time_grain` | `VARCHAR` | 否 | 否 | 时间粒度 | `month` |
| `raw_format` | `VARCHAR` | 否 | 否 | 原始文件格式 | `xlsx` |
| `target_table` | `VARCHAR` | 否 | 否 | 清洗后目标表 | `ods_fact_vehicle_prod_sales_monthly` |
| `load_status` | `VARCHAR` | 否 | 否 | 入库状态 | `loaded` |

### 6.2 `ods_fact_vehicle_prod_sales_monthly` 汽车品牌车型月度产销表

来源：`1汽车分品牌产销(95家车企，768个车型，201512-202210月度数据).xlsx`

该表用于存储汽车厂商和车型维度的月度产销数据，支持厂商排名、车型趋势、产销对比和总汽车销量计算。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 原始字段 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | 清洗生成 | `VPS000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | 清洗生成 | `SRC001` |
| `stat_type` | `VARCHAR` | 否 | 统计类型，产量或销量 | `统计类型` | `销量` |
| `manufacturer_name` | `VARCHAR` | 否 | 制造厂 / 厂商名称 | `制造厂` | `特斯拉(上海)` |
| `model_name` | `VARCHAR` | 否 | 车型名称 | `车型` | `Model3(BEV)` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `车型大类` | `轿车` |
| `data_month` | `VARCHAR` | 否 | 数据月份，统一取月末或月初日期；日期过滤时需 `CAST(data_month AS DATE)` | `数据日期` | `2022-08-31` |
| `current_units` | `DOUBLE` | 是 | 当期值，单位辆 | `当期值(辆)` | `14954` |
| `cumulative_units` | `DOUBLE` | 是 | 年内累计值，单位辆 | `累计值(辆)` | `45754` |
| `last_year_cumulative_units` | `DOUBLE` | 是 | 去年同期累计值，单位辆 | `去年同期累计值(辆)` | `10658` |
| `current_yoy_rate` | `DOUBLE` | 是 | 当期同比，单位 % | `当期同比(%)` | `61.9` |
| `cumulative_yoy_rate` | `DOUBLE` | 是 | 累计同比，单位 % | `累计同比(%)` | `42.3` |

### 6.3 `ods_fact_nev_manufacturer_monthly` 新能源厂商月度产销表

来源：`2新能源汽车分厂商产销(207家厂商，201812-202210月度数据).xlsx`

该表用于存储新能源厂商月度产量和销量数据，支持厂商销量排名、厂商趋势和新能源市场竞争格局分析。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 原始字段 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | 清洗生成 | `NMF000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | 清洗生成 | `SRC002` |
| `manufacturer_name` | `VARCHAR` | 否 | 厂商名称 | `厂商名称` | `比亚迪股份公司` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `车型大类` | `总计` |
| `vehicle_segment` | `VARCHAR` | 是 | 车型细分 | `车型细分` | `总计` |
| `fuel_type` | `VARCHAR` | 是 | 燃料类型 | `燃料类型` | `纯电动` |
| `data_month` | `VARCHAR` | 否 | 数据月份；日期过滤时需 `CAST(data_month AS DATE)` | `数据日期` | `2022-08-31` |
| `production_current_units` | `DOUBLE` | 是 | 当期产量，单位辆 | `产量-当期值(辆)` | `175170` |
| `production_yoy_rate` | `DOUBLE` | 是 | 产量当期同比，单位 % | `产量-当期同比(%)` | `180.05` |
| `production_cumulative_units` | `DOUBLE` | 是 | 产量累计值，单位辆 | `产量-累计值(辆)` | `985169` |
| `production_cumulative_yoy_rate` | `DOUBLE` | 是 | 产量累计同比，单位 % | `产量-累计同比(%)` | `262.11` |
| `sales_current_units` | `DOUBLE` | 是 | 当期销量，单位辆 | `销量-当期值(辆)` | `174915` |
| `sales_yoy_rate` | `DOUBLE` | 是 | 销量当期同比，单位 % | `销量-当期同比(%)` | `184.0` |
| `sales_cumulative_units` | `DOUBLE` | 是 | 销量累计值，单位辆 | `销量-累计值(辆)` | `978795` |
| `sales_cumulative_yoy_rate` | `DOUBLE` | 是 | 销量累计同比，单位 % | `销量-累计同比(%)` | `260.0` |

### 6.4 `ods_fact_nev_overall_monthly` 新能源总体月度产销表

来源：`3新能源汽车总体产销(201812-202210月度数据).xlsx`

该表用于存储新能源汽车总体产销数据，支持新能源总量趋势、纯电 / 插混结构和新能源渗透率计算。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 原始字段 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | 清洗生成 | `NVO000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | 清洗生成 | `SRC003` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `车型大类` | `总计` |
| `vehicle_segment` | `VARCHAR` | 是 | 车型细分 | `车型细分` | `总计` |
| `fuel_type` | `VARCHAR` | 是 | 燃料类型 | `燃料类型` | `插电式混合动力` |
| `data_month` | `VARCHAR` | 否 | 数据月份；日期过滤时需 `CAST(data_month AS DATE)` | `数据日期` | `2022-08-31` |
| `production_current_units` | `DOUBLE` | 是 | 当期产量，单位辆 | `产量-当期值(辆)` | `154550` |
| `production_yoy_rate` | `DOUBLE` | 是 | 产量当期同比，单位 % | `产量-当期同比(%)` | `174.95` |
| `production_cumulative_units` | `DOUBLE` | 是 | 产量累计值，单位辆 | `产量-累计值(辆)` | `856916` |
| `production_cumulative_yoy_rate` | `DOUBLE` | 是 | 产量累计同比，单位 % | `产量-累计同比(%)` | `185.41` |
| `sales_current_units` | `DOUBLE` | 是 | 当期销量，单位辆 | `销量-当期值(辆)` | `144277` |
| `sales_yoy_rate` | `DOUBLE` | 是 | 销量当期同比，单位 % | `销量-当期同比(%)` | `160.0` |
| `sales_cumulative_units` | `DOUBLE` | 是 | 销量累计值，单位辆 | `销量-累计值(辆)` | `820000` |
| `sales_cumulative_yoy_rate` | `DOUBLE` | 是 | 销量累计同比，单位 % | `销量-累计同比(%)` | `180.0` |

### 6.5 `ods_fact_charging_infrastructure_monthly` 充电设施月度指标表

来源：`10国内充电设施数量（省份，月，201602-202302）.xls`

该表建议采用长表结构，用统一的 `metric_name` 和 `metric_value` 承接原始文件中的多指标列，便于后续扩展。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | `CHG000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | `SRC004` |
| `province` | `VARCHAR` | 是 | 省份或地区 | `广东` |
| `data_month` | `VARCHAR` | 否 | 数据月份；日期过滤时需 `CAST(data_month AS DATE)` | `2022-12-31` |
| `metric_name` | `VARCHAR` | 否 | 指标名称 | `公共充电桩数量` |
| `metric_value` | `DOUBLE` | 是 | 指标值 | `383000` |
| `unit` | `VARCHAR` | 是 | 单位 | `台` |

### 6.6 `ods_fact_battery_installation_monthly` 动力电池月度装车指标表

来源：

- `16动力电池装车量分车型（月，201909-202301，10个指标）.xls`
- `17动力电池装车量分材料类型（月，201701-202301，10个指标）.xls`

该表建议采用长表结构，同时用 `dimension_type` 标记分车型或分材料类型，便于统一计算装车量、占比和趋势。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | `BAT000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | `SRC006` |
| `dimension_type` | `VARCHAR` | 否 | 维度类型 | `material_type` |
| `dimension_value` | `VARCHAR` | 否 | 维度值 | `磷酸铁锂` |
| `data_month` | `VARCHAR` | 否 | 数据月份；日期过滤时需 `CAST(data_month AS DATE)` | `2022-12-31` |
| `metric_name` | `VARCHAR` | 否 | 指标名称 | `装车量` |
| `metric_value` | `DOUBLE` | 是 | 指标值 | `15.2` |
| `unit` | `VARCHAR` | 是 | 单位 | `GWh` |

建议枚举值：

| 字段 | 可选值 |
| --- | --- |
| `dimension_type` | `vehicle_type`, `material_type` |
| `metric_name` | `装车量`, `同比增长率`, `累计装车量`, `累计同比增长率` |

### 6.7 `dim_time` 时间维表

该表用于统一时间维度，支持按年、季度、月进行聚合查询。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `date_id` | `VARCHAR` | 否 | 日期主键 | `2022-12-31` |
| `year` | `INT` | 否 | 年份 | `2022` |
| `quarter` | `INT` | 否 | 季度 | `4` |
| `month` | `INT` | 否 | 月份 | `12` |

### 6.8 `dim_manufacturer` 厂商维表

该表包含汽车厂商的统一信息，支持按品牌集团或国别进行汇总。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `manufacturer_id` | `VARCHAR` | 否 | 厂商主键 | `MFG001` |
| `manufacturer_name` | `VARCHAR` | 否 | 厂商名称 | `特斯拉(上海)` |
| `brand_group` | `VARCHAR` | 是 | 品牌集团 | `特斯拉` |
| `country` | `VARCHAR` | 是 | 国别 | `美国` |

### 6.9 `dim_vehicle_model` 车型维表

该表包含车型的统一分类信息，支持按车型大类或燃料类型进行分析。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `model_id` | `VARCHAR` | 否 | 车型主键 | `MDL001` |
| `model_name` | `VARCHAR` | 否 | 车型名称 | `Model3(BEV)` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `轿车` |
| `fuel_type` | `VARCHAR` | 是 | 燃料类型 | `纯电动` |

### 6.10 `dim_province` 省份/地区维表

该表用于统一省份信息，支持按大区或等级汇总。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `province_id` | `VARCHAR` | 否 | 省份主键 | `PRV001` |
| `province` | `VARCHAR` | 否 | 省份名称 | `广东` |
| `region` | `VARCHAR` | 是 | 大区 | `华南` |
| `city_tier` | `VARCHAR` | 是 | 城市等级 | `一线` |

### 6.11 `dim_fuel_type` 燃料类型维表

该表定义燃料的分类信息，用于统计结构占比。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `fuel_type_id` | `VARCHAR` | 否 | 燃料类型主键 | `FUEL001` |
| `fuel_type` | `VARCHAR` | 否 | 燃料名称 | `纯电动` |
| `fuel_category` | `VARCHAR` | 是 | 燃料大类 | `新能源` |

### 6.12 `dim_battery_material` 电池材料维表

该表定义动力电池的材料类型分类。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `material_id` | `VARCHAR` | 否 | 材料主键 | `MAT001` |
| `material_type` | `VARCHAR` | 否 | 材料类型名称 | `三元材料` |

### 6.13 `dim_charging_operator` 充电桩运营商维表

该表定义充电设施运营商的分类信息。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `operator_id` | `VARCHAR` | 否 | 运营商主键 | `OP001` |
| `operator_name` | `VARCHAR` | 否 | 运营商名称 | `特来电` |
| `operator_category` | `VARCHAR` | 是 | 运营商分类 | `公共运营商` |

### 6.14 `dwd_global_ev_sales_yearly` 全球电动汽车年度销量表

用于记录各国家/地区年度的纯电动和插混车辆销量。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `data_year` | `INT` | 否 | 数据年份 | `2022` |
| `country` | `VARCHAR` | 否 | 国家/地区 | `中国` |
| `fuel_type` | `VARCHAR` | 否 | 燃料类型 | `纯电动` |
| `sales_units` | `DOUBLE` | 是 | 销量值 | `5000000` |

### 6.15 `dwd_global_ev_stock_yearly` 全球电动汽车年度保有量表

用于记录各国家/地区年度的电动汽车保有量。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `data_year` | `INT` | 否 | 数据年份 | `2022` |
| `country` | `VARCHAR` | 否 | 国家/地区 | `美国` |
| `fuel_type` | `VARCHAR` | 否 | 燃料类型 | `纯电动` |
| `stock_units` | `DOUBLE` | 是 | 保有量值 | `3000000` |

### 6.16 `dwd_battery_production_monthly` 动力电池月度产量表

用于记录按材料类型分类的动力电池月度产量。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `data_month` | `VARCHAR` | 否 | 数据月份 | `2022-12-31` |
| `material_type` | `VARCHAR` | 否 | 电池材料类型 | `磷酸铁锂` |
| `production_value` | `DOUBLE` | 是 | 产量值 | `100.5` |
| `unit` | `VARCHAR` | 是 | 单位 | `GWh` |

### 6.17 `dwd_vehicle_production_province_monthly` 汽车分省月度产量表

用于记录全国各省份的所有汽车月度产量信息。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `data_month` | `VARCHAR` | 否 | 数据月份 | `2022-12-31` |
| `province` | `VARCHAR` | 否 | 省份名称 | `广东` |
| `production_units` | `DOUBLE` | 是 | 产量值 | `300000` |

### 6.18 `dwd_charging_operator_monthly` 充电桩运营商月度电量表

用于记录各充电设施运营商每月的充电量数据。

| 字段名 | Doris 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `data_month` | `VARCHAR` | 否 | 数据月份 | `2022-12-31` |
| `operator_name` | `VARCHAR` | 否 | 运营商名称 | `特来电` |
| `charging_amount` | `DOUBLE` | 是 | 月度充电量 | `1000000.5` |
| `unit` | `VARCHAR` | 是 | 单位 | `kWh` |

## 7. 标准业务问题与数据表映射

| 标准业务问题 | 需要的表 | 需要的核心字段 |
| --- | --- | --- |
| 2022 年各厂商新能源汽车销量排名如何？ | `ads_nev_manufacturer_sales_rank` | `stat_year`, `manufacturer_name`, `total_sales_units`, `sales_rank` |
| 比亚迪 2021-2022 年新能源汽车销量趋势如何？ | `dws_nev_manufacturer_sales_monthly` | `manufacturer_name`, `data_month`, `sales_units` |
| 纯电动和插电式混合动力车型的销量结构有什么变化？ | `dws_nev_market_monthly` 或后续扩展 ADS 结构表 | `data_month`, `sales_units` |
| 2022 年新能源汽车渗透率的月度趋势如何？ | `ads_nev_penetration_trend` | `data_month`, `nev_sales_units`, `total_vehicle_sales_units`, `penetration_rate` |
| 2022 年哪些车型销量最高？ | `ads_vehicle_model_sales_rank` | `stat_year`, `manufacturer_name`, `model_name`, `total_sales_units`, `sales_rank` |
| 特斯拉上海 Model3 的月度销量趋势如何？ | `dws_vehicle_sales_monthly` | `manufacturer_name`, `model_name`, `data_month`, `sales_units` |
| 汽车产量和销量是否同步增长？ | `dws_vehicle_sales_monthly` | `data_month`, `production_units`, `sales_units` |
| 哪些省份的充电设施数量增长最快？ | `ads_charging_facility_province_distribution` 或 `dws_charging_province_monthly` | `province`, `data_month`, `metric_name`, `metric_value` |
| 不同材料类型动力电池装车量占比如何变化？ | `ads_battery_material_share` | `data_month`, `material_type`, `metric_value`, `share` |
| 不同车型类别的动力电池装车量趋势如何？ | `ads_battery_vehicle_type_share` | `data_month`, `vehicle_type`, `metric_value`, `share` |
