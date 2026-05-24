# AutoBI Agent 指标口径

## 1. 文档目的

本文档定义 AutoBI Agent MVP 阶段使用的汽车产业核心指标，包括指标含义、计算公式、涉及数据表、适用场景和示例 SQL。

该文档将用于：

- 作为 RAG 检索的指标口径知识库。
- 约束 Text-to-SQL 生成逻辑。
- 作为 SQL 测试用例判断结果是否符合业务口径的依据。
- 帮助面试中说明“问数智能体不是只调用大模型，而是依赖可沉淀的指标规范”。

## 2. 指标设计原则

- 指标必须能从当前清洗入库的数据表计算得到。
- 同一指标在不同问题中必须使用同一口径。
- 涉及除法的指标必须使用 `NULLIF(..., 0)` 避免除以 0。
- 时间粒度默认按月，字段统一使用 `data_month`。
- 新能源渗透率等跨表指标必须明确分子、分母和时间对齐方式。
- 对于原始宽表中的多指标列，清洗后优先转成长表的 `metric_name` + `metric_value` 结构。

## 3. 核心指标清单

| 指标名称 | 英文字段 / 别名 | 业务含义 | 主要数据表 |
| --- | --- | --- | --- |
| 汽车销量 | `vehicle_sales_volume` | 指定月份、厂商或车型的汽车销量 | `fact_vehicle_prod_sales_monthly` |
| 汽车产量 | `vehicle_production_volume` | 指定月份、厂商或车型的汽车产量 | `fact_vehicle_prod_sales_monthly` |
| 汽车产销比 | `vehicle_production_sales_ratio` | 汽车产量 / 汽车销量 | `fact_vehicle_prod_sales_monthly` |
| 厂商销量排名 | `manufacturer_sales_rank` | 按销量对厂商排序 | `fact_nev_manufacturer_monthly` |
| 车型销量排名 | `model_sales_rank` | 按销量对车型排序 | `fact_vehicle_prod_sales_monthly` |
| 新能源汽车销量 | `nev_sales_volume` | 新能源汽车当期销量 | `fact_nev_overall_monthly`, `fact_nev_manufacturer_monthly` |
| 新能源汽车产量 | `nev_production_volume` | 新能源汽车当期产量 | `fact_nev_overall_monthly`, `fact_nev_manufacturer_monthly` |
| 新能源渗透率 | `nev_penetration_rate` | 新能源汽车销量 / 汽车总销量 | `fact_nev_overall_monthly`, `fact_vehicle_prod_sales_monthly` |
| 纯电销量占比 | `bev_sales_share` | 纯电动销量 / 新能源总销量 | `fact_nev_overall_monthly` |
| 插混销量占比 | `phev_sales_share` | 插电式混合动力销量 / 新能源总销量 | `fact_nev_overall_monthly` |
| 充电设施数量 | `charging_facility_count` | 指定省份或月份的充电设施数量 | `fact_charging_infrastructure_monthly` |
| 充电设施环比增速 | `charging_facility_mom_rate` | 本月充电设施数量 / 上月数量 - 1 | `fact_charging_infrastructure_monthly` |
| 动力电池装车量 | `battery_installation_volume` | 指定维度下动力电池装车量 | `fact_battery_installation_monthly` |
| 动力电池材料占比 | `battery_material_share` | 某材料类型装车量 / 总装车量 | `fact_battery_installation_monthly` |
| 动力电池车型结构 | `battery_vehicle_type_share` | 某车型类别装车量 / 总装车量 | `fact_battery_installation_monthly` |

## 4. 指标详细口径

### 4.1 汽车销量

业务含义：

指定时间、厂商或车型维度下的汽车销量。

计算公式：

```sql
SUM(current_units)
```

过滤条件：

```sql
stat_type = '销量'
```

涉及表：

- `fact_vehicle_prod_sales_monthly`

示例 SQL：

```sql
SELECT
  model_name,
  SUM(current_units) AS vehicle_sales_volume
FROM fact_vehicle_prod_sales_monthly
WHERE stat_type = '销量'
  AND CAST(data_month AS DATE) BETWEEN DATE '2022-01-01' AND DATE '2022-12-31'
GROUP BY model_name
ORDER BY vehicle_sales_volume DESC
LIMIT 20;
```

### 4.2 汽车产量

业务含义：

指定时间、厂商或车型维度下的汽车产量。

计算公式：

```sql
SUM(current_units)
```

过滤条件：

```sql
stat_type = '产量'
```

涉及表：

- `fact_vehicle_prod_sales_monthly`

示例 SQL：

```sql
SELECT
  data_month,
  SUM(current_units) AS vehicle_production_volume
FROM fact_vehicle_prod_sales_monthly
WHERE stat_type = '产量'
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.3 汽车产销比

业务含义：

汽车产量与销量的比值，用于观察供需是否同步。

计算公式：

```sql
SUM(CASE WHEN stat_type = '产量' THEN current_units ELSE 0 END)
/ NULLIF(SUM(CASE WHEN stat_type = '销量' THEN current_units ELSE 0 END), 0)
```

涉及表：

- `fact_vehicle_prod_sales_monthly`

示例 SQL：

```sql
SELECT
  data_month,
  SUM(CASE WHEN stat_type = '产量' THEN current_units ELSE 0 END)
    / NULLIF(SUM(CASE WHEN stat_type = '销量' THEN current_units ELSE 0 END), 0) AS vehicle_production_sales_ratio
FROM fact_vehicle_prod_sales_monthly
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.4 厂商销量排名

业务含义：

按照指定时间范围内的新能源汽车销量对厂商进行排序。

计算公式：

```sql
SUM(sales_current_units)
```

涉及表：

- `fact_nev_manufacturer_monthly`

示例 SQL：

```sql
SELECT
  manufacturer_name,
  SUM(sales_current_units) AS nev_sales_volume
FROM fact_nev_manufacturer_monthly
WHERE CAST(data_month AS DATE) BETWEEN DATE '2022-01-01' AND DATE '2022-12-31'
  AND vehicle_category = '总计'
GROUP BY manufacturer_name
ORDER BY nev_sales_volume DESC
LIMIT 20;
```

### 4.5 车型销量排名

业务含义：

按照指定时间范围内的销量对车型进行排序。

计算公式：

```sql
SUM(current_units)
```

过滤条件：

```sql
stat_type = '销量'
```

涉及表：

- `fact_vehicle_prod_sales_monthly`

示例 SQL：

```sql
SELECT
  model_name,
  SUM(current_units) AS model_sales_volume
FROM fact_vehicle_prod_sales_monthly
WHERE stat_type = '销量'
  AND CAST(data_month AS DATE) BETWEEN DATE '2022-01-01' AND DATE '2022-12-31'
GROUP BY model_name
ORDER BY model_sales_volume DESC
LIMIT 20;
```

### 4.6 新能源汽车销量

业务含义：

指定月份或燃料类型下的新能源汽车销量。

计算公式：

```sql
SUM(sales_current_units)
```

涉及表：

- `fact_nev_overall_monthly`
- `fact_nev_manufacturer_monthly`

使用规则：

- 分析总体新能源销量时，优先使用 `fact_nev_overall_monthly`。
- 分析厂商新能源销量时，使用 `fact_nev_manufacturer_monthly`。

示例 SQL：

```sql
SELECT
  data_month,
  SUM(sales_current_units) AS nev_sales_volume
FROM fact_nev_overall_monthly
WHERE vehicle_category = '总计'
  AND vehicle_segment = '总计'
  AND fuel_type = '总计'
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.7 新能源汽车产量

业务含义：

指定月份或燃料类型下的新能源汽车产量。

计算公式：

```sql
SUM(production_current_units)
```

涉及表：

- `fact_nev_overall_monthly`
- `fact_nev_manufacturer_monthly`

示例 SQL：

```sql
SELECT
  data_month,
  SUM(production_current_units) AS nev_production_volume
FROM fact_nev_overall_monthly
WHERE vehicle_category = '总计'
  AND vehicle_segment = '总计'
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.8 新能源渗透率

业务含义：

新能源汽车销量占汽车总销量的比例，用于衡量新能源汽车在整体汽车市场中的渗透程度。

计算公式：

```sql
新能源渗透率 = 新能源汽车销量 / 汽车总销量
```

SQL 口径：

```sql
SUM(nev.sales_current_units)
/ NULLIF(SUM(total_vehicle.vehicle_sales_units), 0)
```

分子：

- `fact_nev_overall_monthly.sales_current_units`
- 筛选 `vehicle_category = '总计'`、`vehicle_segment = '总计'`、`fuel_type = '总计'`

分母：

- `fact_vehicle_prod_sales_monthly.current_units`
- 筛选 `stat_type = '销量'`
- 按 `data_month` 汇总

示例 SQL：

```sql
WITH total_vehicle AS (
  SELECT
    data_month,
    SUM(current_units) AS total_vehicle_sales
  FROM fact_vehicle_prod_sales_monthly
  WHERE stat_type = '销量'
  GROUP BY data_month
),
nev AS (
  SELECT
    data_month,
    SUM(sales_current_units) AS nev_sales
  FROM fact_nev_overall_monthly
  WHERE vehicle_category = '总计'
    AND vehicle_segment = '总计'
    AND fuel_type = '总计'
  GROUP BY data_month
)
SELECT
  nev.data_month,
  nev.nev_sales / NULLIF(total_vehicle.total_vehicle_sales, 0) AS nev_penetration_rate
FROM nev
JOIN total_vehicle ON nev.data_month = total_vehicle.data_month
ORDER BY nev.data_month
LIMIT 100;
```

注意：

- 该指标必须按同一月份对齐。
- 如果总汽车销量存在车型重复或汇总口径冲突，需要在数据清洗阶段标记可用于总量计算的记录。

### 4.9 纯电销量占比

业务含义：

纯电动汽车销量占新能源汽车销量的比例。

计算公式：

```sql
纯电销量 / 新能源总销量
```

示例 SQL：

```sql
SELECT
  data_month,
  SUM(CASE WHEN fuel_type = '纯电动' THEN sales_current_units ELSE 0 END)
    / NULLIF(SUM(sales_current_units), 0) AS bev_sales_share
FROM fact_nev_overall_monthly
WHERE vehicle_category = '总计'
  AND vehicle_segment = '总计'
  AND fuel_type IN ('纯电动', '插电式混合动力')
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.10 插混销量占比

业务含义：

插电式混合动力汽车销量占新能源汽车销量的比例。

计算公式：

```sql
插电式混合动力销量 / 新能源总销量
```

示例 SQL：

```sql
SELECT
  data_month,
  SUM(CASE WHEN fuel_type = '插电式混合动力' THEN sales_current_units ELSE 0 END)
    / NULLIF(SUM(sales_current_units), 0) AS phev_sales_share
FROM fact_nev_overall_monthly
WHERE vehicle_category = '总计'
  AND vehicle_segment = '总计'
  AND fuel_type IN ('纯电动', '插电式混合动力')
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.11 充电设施数量

业务含义：

指定省份或月份的充电设施数量。

计算公式：

```sql
SUM(metric_value)
```

涉及表：

- `fact_charging_infrastructure_monthly`

过滤条件：

```sql
metric_name IN ('公共充电桩数量', '充电设施总量')
```

示例 SQL：

```sql
SELECT
  province,
  SUM(metric_value) AS charging_facility_count
FROM fact_charging_infrastructure_monthly
WHERE CAST(data_month AS DATE) = DATE '2022-12-31'
  AND metric_name = '公共充电桩数量'
GROUP BY province
ORDER BY charging_facility_count DESC
LIMIT 20;
```

### 4.12 充电设施环比增速

业务含义：

本月充电设施数量相对上月的增长率。

计算公式：

```sql
(本月数量 - 上月数量) / 上月数量
```

示例 SQL：

```sql
WITH monthly AS (
  SELECT
    province,
    data_month,
    SUM(metric_value) AS charging_facility_count
  FROM fact_charging_infrastructure_monthly
  WHERE metric_name = '公共充电桩数量'
  GROUP BY province, data_month
),
lagged AS (
  SELECT
    province,
    data_month,
    charging_facility_count,
    LAG(charging_facility_count) OVER (PARTITION BY province ORDER BY data_month) AS prev_count
  FROM monthly
)
SELECT
  province,
  data_month,
  (charging_facility_count - prev_count) / NULLIF(prev_count, 0) AS charging_facility_mom_rate
FROM lagged
WHERE prev_count IS NOT NULL
ORDER BY charging_facility_mom_rate DESC
LIMIT 20;
```

### 4.13 动力电池装车量

业务含义：

指定材料类型、车型类别或月份下的动力电池装车规模。

计算公式：

```sql
SUM(metric_value)
```

涉及表：

- `fact_battery_installation_monthly`

过滤条件：

```sql
metric_name = '装车量'
```

示例 SQL：

```sql
SELECT
  data_month,
  SUM(metric_value) AS battery_installation_volume
FROM fact_battery_installation_monthly
WHERE metric_name = '装车量'
GROUP BY data_month
ORDER BY data_month
LIMIT 100;
```

### 4.14 动力电池材料占比

业务含义：

某类动力电池材料装车量占总装车量的比例。

计算公式：

```sql
某材料装车量 / 总装车量
```

示例 SQL：

```sql
SELECT
  data_month,
  dimension_value AS material_type,
  SUM(metric_value)
    / NULLIF(SUM(SUM(metric_value)) OVER (PARTITION BY data_month), 0) AS battery_material_share
FROM fact_battery_installation_monthly
WHERE metric_name = '装车量'
  AND dimension_type = 'material_type'
GROUP BY data_month, dimension_value
ORDER BY data_month, battery_material_share DESC
LIMIT 100;
```

### 4.15 动力电池车型结构

业务含义：

某车型类别动力电池装车量占总装车量的比例。

计算公式：

```sql
某车型类别装车量 / 总装车量
```

示例 SQL：

```sql
SELECT
  data_month,
  dimension_value AS vehicle_type,
  SUM(metric_value)
    / NULLIF(SUM(SUM(metric_value)) OVER (PARTITION BY data_month), 0) AS battery_vehicle_type_share
FROM fact_battery_installation_monthly
WHERE metric_name = '装车量'
  AND dimension_type = 'vehicle_type'
GROUP BY data_month, dimension_value
ORDER BY data_month, battery_vehicle_type_share DESC
LIMIT 100;
```

## 5. 时间字段使用规范

| 分析对象 | 推荐时间字段 |
| --- | --- |
| 汽车品牌 / 车型产销 | `fact_vehicle_prod_sales_monthly.data_month` |
| 新能源厂商产销 | `fact_nev_manufacturer_monthly.data_month` |
| 新能源总体产销 | `fact_nev_overall_monthly.data_month` |
| 充电设施 | `fact_charging_infrastructure_monthly.data_month` |
| 动力电池装车量 | `fact_battery_installation_monthly.data_month` |

## 6. 标准业务问题与指标映射

| 标准业务问题 | 核心指标 | 推荐图表 |
| --- | --- | --- |
| 2022 年各厂商新能源汽车销量排名如何？ | 厂商销量排名、新能源汽车销量 | 柱状图 |
| 比亚迪 2021-2022 年新能源汽车销量趋势如何？ | 新能源汽车销量 | 折线图 |
| 纯电动和插电式混合动力车型的销量结构有什么变化？ | 纯电销量占比、插混销量占比 | 堆叠柱状图或折线图 |
| 2022 年新能源汽车渗透率的月度趋势如何？ | 新能源渗透率 | 折线图 |
| 2022 年哪些车型销量最高？ | 车型销量排名 | 柱状图 |
| 特斯拉上海 Model3 的月度销量趋势如何？ | 汽车销量 | 折线图 |
| 汽车产量和销量是否同步增长？ | 汽车产量、汽车销量、汽车产销比 | 双折线图 |
| 哪些省份的充电设施数量增长最快？ | 充电设施环比增速 | 柱状图 |
| 不同材料类型动力电池装车量占比如何变化？ | 动力电池材料占比 | 堆叠柱状图 |
| 不同车型类别的动力电池装车量趋势如何？ | 动力电池装车量、动力电池车型结构 | 折线图 |

## 7. Text-to-SQL 生成约束

后续 Text-to-SQL Prompt 应遵守以下规则：

1. 只能使用数据字典中定义的表和字段。
2. 涉及销量、产量时，必须区分汽车总量、新能源总量、厂商维度和车型维度。
3. 涉及新能源汽车渗透率时，必须按同一 `data_month` 对齐分子和分母。
4. 涉及占比、增速和比率时，必须使用 `NULLIF(..., 0)` 防止除以 0。
5. 查询结果默认添加 `LIMIT 100`。
6. 不允许生成 `INSERT`、`UPDATE`、`DELETE`、`DROP`、`ALTER` 等非只读 SQL。

## 8. 指标验收标准

MVP 阶段至少需要支持以下指标：

- 汽车销量。
- 汽车产量。
- 汽车产销比。
- 厂商销量排名。
- 车型销量排名。
- 新能源汽车销量。
- 新能源渗透率。
- 纯电 / 插混销量结构。
- 充电设施数量和环比增速。
- 动力电池装车量和结构占比。

验收方式：

- 每个指标至少有 1 个标准业务问题覆盖。
- 每个指标至少有 1 条可执行 SQL 示例。
- 自动生成 SQL 时，应优先匹配本文档中的指标口径。
