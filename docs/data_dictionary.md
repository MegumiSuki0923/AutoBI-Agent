# AutoBI Agent 数据字典

## 1. 文档目的

本文档定义 AutoBI Agent MVP 阶段使用的汽车产业数据表。原始数据来自 `data/raw_data` 下的多源 Excel 文件，清洗后统一写入本地 DuckDB 数据库：

```text
data/autobi.duckdb
```

数据字典的作用：

- 记录原始数据源和清洗后的目标表。
- 明确字段名称、DuckDB 类型、业务含义和示例值。
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
| `dim_data_source` | 数据源维表 | 维度表 | 文件清单 | 记录原始文件、主题、粒度和入库状态 |
| `fact_vehicle_prod_sales_monthly` | 汽车品牌车型月度产销表 | 事实表 | `SRC001` | 支持汽车厂商、车型、产量、销量、同比分析 |
| `fact_nev_manufacturer_monthly` | 新能源厂商月度产销表 | 事实表 | `SRC002` | 支持新能源厂商销量排名和趋势分析 |
| `fact_nev_overall_monthly` | 新能源总体月度产销表 | 事实表 | `SRC003` | 支持新能源总体销量、燃料类型结构和渗透率分析 |
| `fact_charging_infrastructure_monthly` | 充电设施月度指标表 | 事实表 | `SRC004` | 支持省份充电设施数量和增速分析 |
| `fact_battery_installation_monthly` | 动力电池月度装车指标表 | 事实表 | `SRC005`, `SRC006` | 支持电池装车量、材料类型和车型类别分析 |

## 5. 表关系

```text
dim_data_source.source_id
  -> fact_vehicle_prod_sales_monthly.source_id
  -> fact_nev_manufacturer_monthly.source_id
  -> fact_nev_overall_monthly.source_id
  -> fact_charging_infrastructure_monthly.source_id
  -> fact_battery_installation_monthly.source_id
```

业务关联说明：

- 各事实表通过 `data_month` 对齐月度时间粒度。
- 新能源渗透率需要将 `fact_nev_overall_monthly` 的新能源销量与 `fact_vehicle_prod_sales_monthly` 的总汽车销量按月对齐。
- 厂商、车型、燃料类型、材料类型、车型类别等维度暂不单独建维表，MVP 阶段直接保存在事实表中。
- 后续如果字段稳定，可再拆分 `dim_manufacturer`、`dim_vehicle_model`、`dim_region` 等维表。

## 6. 表结构设计

### 6.1 `dim_data_source` 数据源维表

| 字段名 | DuckDB 类型 | 是否主键 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `source_id` | `VARCHAR` | 是 | 否 | 数据源 ID | `SRC001` |
| `file_name` | `VARCHAR` | 否 | 否 | 原始文件名 | `1汽车分品牌产销...xlsx` |
| `topic` | `VARCHAR` | 否 | 否 | 数据主题 | `汽车品牌车型产销` |
| `time_grain` | `VARCHAR` | 否 | 否 | 时间粒度 | `month` |
| `raw_format` | `VARCHAR` | 否 | 否 | 原始文件格式 | `xlsx` |
| `target_table` | `VARCHAR` | 否 | 否 | 清洗后目标表 | `fact_vehicle_prod_sales_monthly` |
| `load_status` | `VARCHAR` | 否 | 否 | 入库状态 | `loaded` |

### 6.2 `fact_vehicle_prod_sales_monthly` 汽车品牌车型月度产销表

来源：`1汽车分品牌产销(95家车企，768个车型，201512-202210月度数据).xlsx`

该表用于存储汽车厂商和车型维度的月度产销数据，支持厂商排名、车型趋势、产销对比和总汽车销量计算。

| 字段名 | DuckDB 类型 | 是否可为空 | 含义 | 原始字段 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | 清洗生成 | `VPS000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | 清洗生成 | `SRC001` |
| `stat_type` | `VARCHAR` | 否 | 统计类型，产量或销量 | `统计类型` | `销量` |
| `manufacturer_name` | `VARCHAR` | 否 | 制造厂 / 厂商名称 | `制造厂` | `特斯拉(上海)` |
| `model_name` | `VARCHAR` | 否 | 车型名称 | `车型` | `Model3(BEV)` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `车型大类` | `轿车` |
| `data_month` | `DATE` | 否 | 数据月份，统一取月末或月初日期 | `数据日期` | `2022-08-31` |
| `current_units` | `DOUBLE` | 是 | 当期值，单位辆 | `当期值(辆)` | `14954` |
| `cumulative_units` | `DOUBLE` | 是 | 年内累计值，单位辆 | `累计值(辆)` | `45754` |
| `last_year_cumulative_units` | `DOUBLE` | 是 | 去年同期累计值，单位辆 | `去年同期累计值(辆)` | `10658` |
| `current_yoy_rate` | `DOUBLE` | 是 | 当期同比，单位 % | `当期同比(%)` | `61.9` |
| `cumulative_yoy_rate` | `DOUBLE` | 是 | 累计同比，单位 % | `累计同比(%)` | `42.3` |

### 6.3 `fact_nev_manufacturer_monthly` 新能源厂商月度产销表

来源：`2新能源汽车分厂商产销(207家厂商，201812-202210月度数据).xlsx`

该表用于存储新能源厂商月度产量和销量数据，支持厂商销量排名、厂商趋势和新能源市场竞争格局分析。

| 字段名 | DuckDB 类型 | 是否可为空 | 含义 | 原始字段 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | 清洗生成 | `NMF000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | 清洗生成 | `SRC002` |
| `manufacturer_name` | `VARCHAR` | 否 | 厂商名称 | `厂商名称` | `比亚迪股份公司` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `车型大类` | `总计` |
| `vehicle_segment` | `VARCHAR` | 是 | 车型细分 | `车型细分` | `总计` |
| `fuel_type` | `VARCHAR` | 是 | 燃料类型 | `燃料类型` | `纯电动` |
| `data_month` | `DATE` | 否 | 数据月份 | `数据日期` | `2022-08-31` |
| `production_current_units` | `DOUBLE` | 是 | 当期产量，单位辆 | `产量-当期值(辆)` | `175170` |
| `production_yoy_rate` | `DOUBLE` | 是 | 产量当期同比，单位 % | `产量-当期同比(%)` | `180.05` |
| `production_cumulative_units` | `DOUBLE` | 是 | 产量累计值，单位辆 | `产量-累计值(辆)` | `985169` |
| `production_cumulative_yoy_rate` | `DOUBLE` | 是 | 产量累计同比，单位 % | `产量-累计同比(%)` | `262.11` |
| `sales_current_units` | `DOUBLE` | 是 | 当期销量，单位辆 | `销量-当期值(辆)` | `174915` |
| `sales_yoy_rate` | `DOUBLE` | 是 | 销量当期同比，单位 % | `销量-当期同比(%)` | `184.0` |
| `sales_cumulative_units` | `DOUBLE` | 是 | 销量累计值，单位辆 | `销量-累计值(辆)` | `978795` |
| `sales_cumulative_yoy_rate` | `DOUBLE` | 是 | 销量累计同比，单位 % | `销量-累计同比(%)` | `260.0` |

### 6.4 `fact_nev_overall_monthly` 新能源总体月度产销表

来源：`3新能源汽车总体产销(201812-202210月度数据).xlsx`

该表用于存储新能源汽车总体产销数据，支持新能源总量趋势、纯电 / 插混结构和新能源渗透率计算。

| 字段名 | DuckDB 类型 | 是否可为空 | 含义 | 原始字段 | 示例 |
| --- | --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | 清洗生成 | `NVO000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | 清洗生成 | `SRC003` |
| `vehicle_category` | `VARCHAR` | 是 | 车型大类 | `车型大类` | `总计` |
| `vehicle_segment` | `VARCHAR` | 是 | 车型细分 | `车型细分` | `总计` |
| `fuel_type` | `VARCHAR` | 是 | 燃料类型 | `燃料类型` | `插电式混合动力` |
| `data_month` | `DATE` | 否 | 数据月份 | `数据日期` | `2022-08-31` |
| `production_current_units` | `DOUBLE` | 是 | 当期产量，单位辆 | `产量-当期值(辆)` | `154550` |
| `production_yoy_rate` | `DOUBLE` | 是 | 产量当期同比，单位 % | `产量-当期同比(%)` | `174.95` |
| `production_cumulative_units` | `DOUBLE` | 是 | 产量累计值，单位辆 | `产量-累计值(辆)` | `856916` |
| `production_cumulative_yoy_rate` | `DOUBLE` | 是 | 产量累计同比，单位 % | `产量-累计同比(%)` | `185.41` |
| `sales_current_units` | `DOUBLE` | 是 | 当期销量，单位辆 | `销量-当期值(辆)` | `144277` |
| `sales_yoy_rate` | `DOUBLE` | 是 | 销量当期同比，单位 % | `销量-当期同比(%)` | `160.0` |
| `sales_cumulative_units` | `DOUBLE` | 是 | 销量累计值，单位辆 | `销量-累计值(辆)` | `820000` |
| `sales_cumulative_yoy_rate` | `DOUBLE` | 是 | 销量累计同比，单位 % | `销量-累计同比(%)` | `180.0` |

### 6.5 `fact_charging_infrastructure_monthly` 充电设施月度指标表

来源：`10国内充电设施数量（省份，月，201602-202302）.xls`

该表建议采用长表结构，用统一的 `metric_name` 和 `metric_value` 承接原始文件中的多指标列，便于后续扩展。

| 字段名 | DuckDB 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | `CHG000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | `SRC004` |
| `province` | `VARCHAR` | 是 | 省份或地区 | `广东` |
| `data_month` | `DATE` | 否 | 数据月份 | `2022-12-31` |
| `metric_name` | `VARCHAR` | 否 | 指标名称 | `公共充电桩数量` |
| `metric_value` | `DOUBLE` | 是 | 指标值 | `383000` |
| `unit` | `VARCHAR` | 是 | 单位 | `台` |

### 6.6 `fact_battery_installation_monthly` 动力电池月度装车指标表

来源：

- `16动力电池装车量分车型（月，201909-202301，10个指标）.xls`
- `17动力电池装车量分材料类型（月，201701-202301，10个指标）.xls`

该表建议采用长表结构，同时用 `dimension_type` 标记分车型或分材料类型，便于统一计算装车量、占比和趋势。

| 字段名 | DuckDB 类型 | 是否可为空 | 含义 | 示例 |
| --- | --- | --- | --- | --- |
| `record_id` | `VARCHAR` | 否 | 清洗后的记录 ID | `BAT000001` |
| `source_id` | `VARCHAR` | 否 | 数据源 ID | `SRC006` |
| `dimension_type` | `VARCHAR` | 否 | 维度类型 | `material_type` |
| `dimension_value` | `VARCHAR` | 否 | 维度值 | `磷酸铁锂` |
| `data_month` | `DATE` | 否 | 数据月份 | `2022-12-31` |
| `metric_name` | `VARCHAR` | 否 | 指标名称 | `装车量` |
| `metric_value` | `DOUBLE` | 是 | 指标值 | `15.2` |
| `unit` | `VARCHAR` | 是 | 单位 | `GWh` |

建议枚举值：

| 字段 | 可选值 |
| --- | --- |
| `dimension_type` | `vehicle_type`, `material_type` |
| `metric_name` | `装车量`, `同比增长率`, `累计装车量`, `累计同比增长率` |

## 7. 标准业务问题与数据表映射

| 标准业务问题 | 需要的表 | 需要的核心字段 |
| --- | --- | --- |
| 2022 年各厂商新能源汽车销量排名如何？ | `fact_nev_manufacturer_monthly` | `manufacturer_name`, `data_month`, `sales_current_units` |
| 比亚迪 2021-2022 年新能源汽车销量趋势如何？ | `fact_nev_manufacturer_monthly` | `manufacturer_name`, `data_month`, `sales_current_units` |
| 纯电动和插电式混合动力车型的销量结构有什么变化？ | `fact_nev_overall_monthly` | `fuel_type`, `data_month`, `sales_current_units` |
| 2022 年新能源汽车渗透率的月度趋势如何？ | `fact_nev_overall_monthly`, `fact_vehicle_prod_sales_monthly` | `data_month`, `sales_current_units`, `current_units`, `stat_type` |
| 2022 年哪些车型销量最高？ | `fact_vehicle_prod_sales_monthly` | `model_name`, `data_month`, `current_units`, `stat_type` |
| 特斯拉上海 Model3 的月度销量趋势如何？ | `fact_vehicle_prod_sales_monthly` | `manufacturer_name`, `model_name`, `data_month`, `current_units` |
| 汽车产量和销量是否同步增长？ | `fact_vehicle_prod_sales_monthly` | `stat_type`, `data_month`, `current_units` |
| 哪些省份的充电设施数量增长最快？ | `fact_charging_infrastructure_monthly` | `province`, `data_month`, `metric_name`, `metric_value` |
| 不同材料类型动力电池装车量占比如何变化？ | `fact_battery_installation_monthly` | `dimension_type`, `dimension_value`, `data_month`, `metric_value` |
| 不同车型类别的动力电池装车量趋势如何？ | `fact_battery_installation_monthly` | `dimension_type`, `dimension_value`, `data_month`, `metric_value` |
