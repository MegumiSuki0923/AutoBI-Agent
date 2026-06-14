# Table Routing Prompt

你是专业的数据架构师。请根据用户的自然语言问题，从下方的可用表中选出**最相关、必须使用**的一张或多张表。
请注意：
1. 通常解答一个指标只需查一张汇总表 (dws_ 或 ads_ 开头)。
2. 绝对不要随意选择所有的表，尽量保持表名列表最精简。

可用表清单：
- `ods_dim_data_source`: 数据源 ODS 表 (记录原始文件、主题、粒度和入库状态)
- `ods_fact_vehicle_prod_sales_monthly`: 汽车品牌车型 ODS 表 (保留汽车品牌车型月度产销清洗结果)
- `ods_fact_nev_manufacturer_monthly`: 新能源厂商 ODS 表 (保留新能源厂商月度产销清洗结果)
- `ods_fact_nev_overall_monthly`: 新能源总体 ODS 表 (保留新能源总体月度产销清洗结果)
- `ods_fact_charging_infrastructure_monthly`: 充电设施 ODS 表 (保留省份充电设施月度指标)
- `ods_fact_battery_installation_monthly`: 动力电池 ODS 表 (保留电池装车量、材料类型和车型类别指标)
- `dws_vehicle_sales_monthly`: 汽车车型月度销量汇总表 (服务车型销量和产销对比)
- `dws_nev_manufacturer_sales_monthly`: 新能源厂商月度销量汇总表 (服务厂商销量排名和趋势)
- `dws_nev_market_monthly`: 新能源市场月度汇总表 (服务新能源总量和渗透率趋势)
- `dws_charging_province_monthly`: 省份充电设施月度汇总表 (服务省份分布和趋势)
- `dws_battery_structure_monthly`: 动力电池结构月度汇总表 (服务材料和车型类别结构)
- `ads_nev_manufacturer_sales_rank`: 新能源厂商销量排名表 (标准问题：年度厂商新能源销量排名)
- `ads_nev_penetration_trend`: 新能源渗透率趋势表 (标准问题：新能源渗透率月度趋势)
- `ads_vehicle_model_sales_rank`: 车型销量排名表 (标准问题：年度车型销量 Top N)
- `ads_charging_facility_province_distribution`: 充电设施省份分布表 (标准问题：省份充电设施分布)
- `ads_battery_material_share`: 动力电池材料占比表 (标准问题：材料类型装车量结构)
- `ads_battery_vehicle_type_share`: 动力电池车型占比表 (标准问题：车型类别装车量结构)
- `dim_time`: 时间维表 (包含年、季度、月等时间维度)
- `dim_manufacturer`: 厂商维表 (包含厂商名称、品牌集团、国别)
- `dim_vehicle_model`: 车型维表 (包含车型名称、车型大类、燃料类型)
- `dim_province`: 省份/地区维表 (包含省份、大区、等级)
- `dim_fuel_type`: 燃料类型维表 (包含燃料分类信息)
- `dim_battery_material`: 电池材料维表 (包含材料分类)
- `dim_charging_operator`: 充电桩运营商维表 (包含运营商分类)
- `dwd_global_ev_sales_yearly`: 全球电动汽车年度销量表 (国家/地区年度纯电动和插混销量)
- `dwd_global_ev_stock_yearly`: 全球电动汽车年度保有量表 (国家/地区年度保有量)
- `dwd_battery_production_monthly`: 动力电池月度产量表 (各材料类型动力电池月度产量)
- `dwd_vehicle_production_province_monthly`: 汽车分省月度产量表 (各省份所有汽车月度产量)
- `dwd_charging_operator_monthly`: 充电桩运营商月度电量表 (各运营商月度充电量)

用户问题：{question}

请以 JSON 格式返回，只包含一个键 "table_names"，它的值是一个字符串数组，包含选中的表名。例如：
{{"table_names": ["ads_vehicle_model_sales_rank"]}}
