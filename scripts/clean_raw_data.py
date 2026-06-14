"""
clean_raw_data.py — 原始 Excel 数据清洗脚本（Excel → CSV）

读取 data/raw_data/ 下的 6 个 MVP 数据源，执行字段映射、脏数据过滤、
去重和标准化，输出干净的 CSV 文件至 data/cleaned/ 目录。

基于 inspect_raw_data.py 的探查结论（scripts/report.md），本脚本处理以下已知问题：
  1. SRC001 汽车品牌车型产销：按业务键去重（257 行重复，46 组）
  2. SRC002 NEV 厂商表：按业务键去重（货车/货车-专用货车 交叉组合，7638 行）
  3. SRC003 NEV 总体表：按业务键去重（45 行重复）
  4. SRC004 充电设施表：完整省份白名单 + 正确解析所有指标类别
  5. SRC005/SRC006 电池表：统一 metric_name 解析逻辑
  6. SRC006 合计列单位 GWh → MWh 统一换算

保留但不过滤的情况：
  - stat_type='出口'（合法业务数据，文档中需补充说明）
  - 负值 current_units / sales_current_units（退货冲销，正常业务数据）

使用方法：
    python scripts/clean_raw_data.py

产出：
    data/cleaned/dim_data_source.csv
    data/cleaned/fact_vehicle_prod_sales_monthly.csv
    data/cleaned/fact_nev_manufacturer_monthly.csv
    data/cleaned/fact_nev_overall_monthly.csv
    data/cleaned/fact_charging_infrastructure_monthly.csv
    data/cleaned/fact_battery_installation_monthly.csv
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


# ────────────────────────────── 路径常量 ──────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"

VEHICLE_FILE = RAW_DATA_DIR / "1汽车分品牌产销(95家车企，768个车型，201512-202210月度数据).xlsx"
NEV_MANUFACTURER_FILE = RAW_DATA_DIR / "2新能源汽车分厂商产销(207家厂商，201812-202210月度数据).xlsx"
NEV_OVERALL_FILE = RAW_DATA_DIR / "3新能源汽车总体产销(201812-202210月度数据).xlsx"
CHARGING_FILE = RAW_DATA_DIR / "10国内充电设施数量（省份，月，201602-202302）.xls"
BATTERY_VEHICLE_FILE = RAW_DATA_DIR / "16动力电池装车量分车型（月，201909-202301，10个指标）.xls"
BATTERY_MATERIAL_FILE = RAW_DATA_DIR / "17动力电池装车量分材料类型（月，201701-202301，10个指标）.xls"


# ────────────────────────────── 通用工具函数 ──────────────────────────────

def _to_number(series: pd.Series) -> pd.Series:
    """将 Series 强制转换为数值类型，无法转换的变为 NaN"""
    return pd.to_numeric(series, errors="coerce")


def _to_month(series: pd.Series) -> pd.Series:
    """将 Series 转换为日期类型，只保留日期部分（用于按月对齐）"""
    return pd.to_datetime(series, errors="coerce").dt.date


def _with_record_id(df: pd.DataFrame, prefix: str) -> list[str]:
    """生成带有特定前缀的定长自增记录 ID，例如 'VPS000001'"""
    return [f"{prefix}{i:06d}" for i in range(1, len(df) + 1)]


def _dedup_by_biz_keys(
    df: pd.DataFrame, biz_keys: list[str], label: str
) -> pd.DataFrame:
    """按业务键去重，保留首条记录，并打印去重统计"""
    before = len(df)
    df = df.drop_duplicates(subset=biz_keys, keep="first")
    after = len(df)
    if before != after:
        print(f"    去重: {before} → {after} (移除 {before - after} 行)")
    return df


# ────────────────────────────── SRC001: 汽车品牌车型产销 ──────────────────────────────

def clean_vehicle_prod_sales() -> pd.DataFrame:
    """
    读取并清洗 SRC001: 汽车分品牌产销数据

    清洗重点（来自 report.md）：
    - 165 行序号为空（子表头行），需过滤
    - 257 行业务键重复（46 组，每组 2 行），按业务键去重
    - stat_type 包含 '产量'、'销量'、'出口' 三种值（保留）
    - current_units 有 113 行负值（退货冲销，保留）
    """
    print("  清洗 SRC001: 汽车品牌车型产销...")
    raw = pd.read_excel(VEHICLE_FILE, engine="openpyxl")

    # 跳过序号为空的子表头行（165 行）
    raw = raw.dropna(subset=["序号"]).copy()

    df = pd.DataFrame(
        {
            "source_id": "SRC001",
            "stat_type": raw["统计类型"].astype("string"),
            "manufacturer_name": raw["制造厂"].astype("string"),
            "model_name": raw["车型"].astype("string"),
            "vehicle_category": raw["车型大类"].astype("string"),
            "data_month": _to_month(raw["数据日期"]),
            "current_units": _to_number(raw["当期值(辆)"]),
            "cumulative_units": _to_number(raw["累计值(辆)"]),
            "last_year_cumulative_units": _to_number(raw["去年同期累计值(辆)"]),
            "current_yoy_rate": _to_number(raw["当期同比(%)"]),
            "current_mom_rate": _to_number(raw["当期环比(%)"]),
            "cumulative_yoy_rate": _to_number(raw["累计同比(%)"]),
            "market_share_rate": _to_number(raw["市占率(%)"]),
        }
    )

    # 丢弃没有时间或统计类型的无效行
    df = df.dropna(subset=["data_month", "stat_type"])

    # 按业务键去重（report.md: 257 行重复，46 组）
    biz_keys = ["manufacturer_name", "model_name", "stat_type", "data_month"]
    df = _dedup_by_biz_keys(df, biz_keys, "SRC001")

    # 去重后重新生成连续 record_id
    df = df.copy()
    df["record_id"] = _with_record_id(df, "VPS")

    print(f"    行数: {len(df)}, stat_type: {df['stat_type'].unique().tolist()}")
    return df


# ────────────────────────────── SRC002: 新能源汽车分厂商产销 ──────────────────────────────

def clean_nev_manufacturer() -> pd.DataFrame:
    """
    读取并清洗 SRC002: 新能源汽车分厂商产销数据

    清洗重点（来自 report.md）：
    - 跳过双层表头的第二行（序号为 NaN）
    - 按业务键 (厂商+大类+细分+燃料+月份) 去重，保留首条
      原因：原始数据对「货车/货车-专用货车」「客车/客车-城市客车」等
      父子分类产生了交叉组合，导致 7,638 行重复
    """
    print("  清洗 SRC002: 新能源汽车分厂商产销...")
    raw = pd.read_excel(NEV_MANUFACTURER_FILE, engine="openpyxl")

    # 跳过双层表头的子表头行
    raw = raw.dropna(subset=["序号"]).copy()

    df = pd.DataFrame(
        {
            "source_id": "SRC002",
            "manufacturer_name": raw["厂商名称"].astype("string"),
            "vehicle_category": raw["车型大类"].astype("string"),
            "vehicle_segment": raw["车型细分"].astype("string"),
            "fuel_type": raw["燃料类型"].astype("string"),
            "data_month": _to_month(raw["数据日期"]),
            "production_current_units": _to_number(raw["产量"]),
            "production_yoy_rate": _to_number(raw["产量_1"]),
            "production_cumulative_units": _to_number(raw["产量_2"]),
            "production_cumulative_yoy_rate": _to_number(raw["产量_3"]),
            "sales_current_units": _to_number(raw["销量"]),
            "sales_yoy_rate": _to_number(raw["销量_4"]),
            "sales_cumulative_units": _to_number(raw["销量_5"]),
            "sales_cumulative_yoy_rate": _to_number(raw["销量_6"]),
        }
    )

    # 丢弃无效行
    df = df.dropna(subset=["data_month", "manufacturer_name"])

    # 按业务键去重（report.md: 7638 行重复，2737 组）
    biz_keys = [
        "manufacturer_name", "vehicle_category", "vehicle_segment",
        "fuel_type", "data_month",
    ]
    df = _dedup_by_biz_keys(df, biz_keys, "SRC002")

    # 重新生成 record_id（去重后序号需连续）
    df = df.copy()
    df["record_id"] = _with_record_id(df, "NMF")

    print(f"    行数: {len(df)}, 厂商数: {df['manufacturer_name'].nunique()}")
    return df


# ────────────────────────────── SRC003: 新能源汽车总体产销 ──────────────────────────────

def clean_nev_overall() -> pd.DataFrame:
    """
    读取并清洗 SRC003: 新能源汽车总体产销数据

    清洗重点（来自 report.md）：
    - 跳过双层表头的第二行（序号异常长文本，45 行）
    - 按业务键去重（report.md: 45 行重复）
    """
    print("  清洗 SRC003: 新能源汽车总体产销...")
    raw = pd.read_excel(NEV_OVERALL_FILE, engine="openpyxl")

    # 跳过子表头行：序号列为异常长文本的行
    # report.md 显示序号列有 45 行异常长文本（阈值 7 字符）
    raw = raw[raw["序号"].apply(lambda x: len(str(x)) <= 7)].copy()

    df = pd.DataFrame(
        {
            "source_id": "SRC003",
            "vehicle_category": raw["车型大类"].astype("string"),
            "vehicle_segment": raw["车型细分"].astype("string"),
            "fuel_type": raw["燃料类型"].astype("string"),
            "data_month": _to_month(raw["数据日期"]),
            "production_current_units": _to_number(raw["产量"]),
            "production_yoy_rate": _to_number(raw["产量_1"]),
            "production_cumulative_units": _to_number(raw["产量_2"]),
            "production_cumulative_yoy_rate": _to_number(raw["产量_3"]),
            "sales_current_units": _to_number(raw["销量"]),
            "sales_yoy_rate": _to_number(raw["销量_4"]),
            "sales_cumulative_units": _to_number(raw["销量_5"]),
            "sales_cumulative_yoy_rate": _to_number(raw["销量_6"]),
        }
    )

    df = df.dropna(subset=["data_month"])

    # 按业务键去重（report.md: 45 行重复）
    biz_keys = ["vehicle_category", "vehicle_segment", "fuel_type", "data_month"]
    df = _dedup_by_biz_keys(df, biz_keys, "SRC003")

    # 重新生成 record_id
    df = df.copy()
    df["record_id"] = _with_record_id(df, "NVO")

    print(f"    行数: {len(df)}, fuel_type: {df['fuel_type'].unique().tolist()}")
    return df


# ────────────────────────────── SRC004: 充电设施 ──────────────────────────────

# 完整省份白名单（来自 report.md 中所有实际出现的省份）
PROVINCE_WHITELIST = frozenset({
    "全国", "北京", "上海", "广东", "江苏", "山东", "安徽", "浙江",
    "湖北", "福建", "河南", "河北", "四川", "天津", "吉林",
})

# 原始列名中非省份的后缀，需要特殊处理
NON_PROVINCE_SUFFIXES = frozenset({
    "交流桩", "直流桩", "同比", "环比", "合计", "总计",
})


def clean_charging_infrastructure() -> pd.DataFrame:
    """
    读取并清洗 SRC004: 充电设施月度指标数据

    清洗重点（来自 report.md）：
    - 原始文件为 Datayes 宽表格式（前 6 行为元数据）
    - 49 个指标列，覆盖 5 大类：
      公共类充电桩数量、公共充电基础设施充电总量、公共充电站数量、
      共享私桩数量、车企随车配建充电设施保有量、换电站保有数量
    - 列名格式多样，需正确解析省份和指标修饰：
      - `公共类充电桩数量_交流桩_全国` → metric=公共充电桩数量(交流桩), province=全国
      - `公共充电基础设施充电总量_同比` → metric=公共充电基础设施充电总量(同比), province=全国
      - `车企随车配建充电设施保有量` → 无后缀，省份=全国
      - `换电站保有数量_总计` → metric=换电站保有数量(总计), province=全国
    """
    print("  清洗 SRC004: 充电设施数量...")
    raw = pd.read_excel(CHARGING_FILE, header=None)

    metrics = raw.iloc[1, 1:].tolist()
    units = raw.iloc[3, 1:].tolist()
    unit_map = dict(zip(metrics, units))

    data = raw.iloc[6:].copy()
    data.columns = ["data_month"] + metrics

    # 宽表转长表
    data = data.melt(id_vars=["data_month"], var_name="raw_metric", value_name="metric_value")

    # 解析每一列的含义
    parsed_rows = []
    for _, row in data.iterrows():
        raw_metric = row["raw_metric"]
        if not isinstance(raw_metric, str):
            continue

        parts = raw_metric.split("_")
        base_metric = parts[0]

        # 标准化指标名：「公共类充电桩数量」→「公共充电桩数量」
        if base_metric == "公共类充电桩数量":
            base_metric = "公共充电桩数量"

        # 根据列名结构解析省份和指标修饰
        if len(parts) == 1:
            # 无后缀，如「公共充电基础设施充电总量」「车企随车配建充电设施保有量」
            province = "全国"
            metric_name = base_metric
        elif len(parts) == 2:
            suffix = parts[1]
            if suffix in PROVINCE_WHITELIST:
                # 「指标名_省份」，正常情况
                province = suffix
                metric_name = base_metric
            elif suffix in NON_PROVINCE_SUFFIXES:
                # 「指标名_同比」「指标名_环比」「指标名_总计」「指标名_合计」
                province = "全国"
                metric_name = f"{base_metric}({suffix})"
            else:
                # 未知后缀，跳过
                continue
        elif len(parts) == 3:
            # 「指标名_桩类型_全国」如「公共充电桩数量_交流桩_全国」
            modifier = parts[1]
            province = parts[2]
            if province not in PROVINCE_WHITELIST:
                continue
            metric_name = f"{base_metric}({modifier})"
        else:
            continue

        parsed_rows.append(
            {
                "data_month": row["data_month"],
                "province": province,
                "metric_name": metric_name,
                "metric_value": row["metric_value"],
                "unit": unit_map.get(row["raw_metric"], ""),
            }
        )

    df = pd.DataFrame(parsed_rows)
    df["source_id"] = "SRC004"
    df["data_month"] = _to_month(df["data_month"])
    df["metric_value"] = _to_number(df["metric_value"])
    df["province"] = df["province"].astype("string")
    df["metric_name"] = df["metric_name"].astype("string")
    df["unit"] = df["unit"].astype("string")

    df = df.dropna(subset=["data_month", "metric_value"]).copy()
    df["record_id"] = _with_record_id(df, "CHG")

    # 输出列顺序
    df = df[["record_id", "source_id", "province", "data_month", "metric_name", "metric_value", "unit"]]

    print(f"    行数: {len(df)}, 省份: {sorted(df['province'].unique().tolist())}")
    print(f"    指标: {sorted(df['metric_name'].unique().tolist())}")
    return df


# ────────────────────────────── SRC005 + SRC006: 动力电池 ──────────────────────────────

# SRC006 中合计列使用 GWh，其他列使用 MWh，需统一为 MWh
GWH_TO_MWH = 1000.0


def _parse_battery_file(file_path: Path, source_id: str, dim_type: str) -> pd.DataFrame:
    """
    通用的动力电池数据清洗函数（处理 Datayes 宽表）

    列名格式：「装车量_动力电池_维度值_当期值/累计值」
    例如：
    - 装车量_动力电池_纯电动乘用车_当期值
    - 装车量_动力电池_三元材料_累计值
    - 装车量_动力电池_合计_当期值
    """
    raw = pd.read_excel(file_path, header=None)

    metrics = raw.iloc[1, 1:].tolist()
    units = raw.iloc[3, 1:].tolist()
    unit_map = dict(zip(metrics, units))

    data = raw.iloc[6:].copy()
    data.columns = ["data_month"] + metrics
    data = data.melt(id_vars=["data_month"], var_name="raw_metric", value_name="metric_value")

    def parse_metric(raw_name: str) -> tuple[str, str] | None:
        """解析列名，返回 (维度值, 指标名)"""
        if not isinstance(raw_name, str):
            return None

        parts = raw_name.split("_")
        if len(parts) < 4:
            return None

        dim_value = parts[2]
        stat_type = parts[3]

        if stat_type == "当期值":
            return dim_value, "装车量"
        elif stat_type == "累计值":
            return dim_value, "累计装车量"
        else:
            return None

    parsed_rows = []
    for _, row in data.iterrows():
        result = parse_metric(row["raw_metric"])
        if result is None:
            continue

        dim_value, metric_name = result
        raw_unit = str(unit_map.get(row["raw_metric"], ""))
        value = row["metric_value"]

        # SRC006 单位统一：GWh → MWh（report.md: 合计列为 GWh，其余为 MWh）
        if raw_unit == "GWh" and pd.notna(value):
            value = value * GWH_TO_MWH
            final_unit = "MWh"
        else:
            final_unit = raw_unit

        parsed_rows.append(
            {
                "data_month": row["data_month"],
                "dimension_type": dim_type,
                "dimension_value": dim_value,
                "metric_name": metric_name,
                "metric_value": value,
                "unit": final_unit,
            }
        )

    df = pd.DataFrame(parsed_rows)
    df["source_id"] = source_id
    df["data_month"] = _to_month(df["data_month"])
    df["metric_value"] = _to_number(df["metric_value"])
    df["dimension_value"] = df["dimension_value"].astype("string")
    df["metric_name"] = df["metric_name"].astype("string")
    df["unit"] = df["unit"].astype("string")

    return df.dropna(subset=["data_month", "metric_value"])


def clean_battery_installation() -> pd.DataFrame:
    """整合 SRC005 和 SRC006，生成统一的动力电池月度装车指标长表"""
    print("  清洗 SRC005 + SRC006: 动力电池装车量...")

    df_vehicle = _parse_battery_file(BATTERY_VEHICLE_FILE, "SRC005", "vehicle_type")
    df_material = _parse_battery_file(BATTERY_MATERIAL_FILE, "SRC006", "material_type")

    df = pd.concat([df_vehicle, df_material], ignore_index=True)
    df["record_id"] = _with_record_id(df, "BAT")

    df = df[["record_id", "source_id", "dimension_type", "dimension_value", "data_month", "metric_name", "metric_value", "unit"]]

    print(f"    行数: {len(df)}, dimension_type: {df['dimension_type'].unique().tolist()}")
    print(f"    dimension_value: {sorted(df['dimension_value'].unique().tolist())}")
    # 验证单位统一
    unit_counts = df["unit"].value_counts().to_dict()
    print(f"    单位分布: {unit_counts}")
    return df


# ────────────────────────────── dim_data_source 维表 ──────────────────────────────

def build_data_source_table() -> pd.DataFrame:
    """生成 dim_data_source 维表（手工维护的数据集元信息）"""
    return pd.DataFrame(
        [
            {
                "source_id": "SRC001",
                "file_name": VEHICLE_FILE.name,
                "topic": "汽车品牌车型产销",
                "time_grain": "month",
                "raw_format": "xlsx",
                "target_table": "fact_vehicle_prod_sales_monthly",
                "load_status": "loaded",
            },
            {
                "source_id": "SRC002",
                "file_name": NEV_MANUFACTURER_FILE.name,
                "topic": "新能源汽车分厂商产销",
                "time_grain": "month",
                "raw_format": "xlsx",
                "target_table": "fact_nev_manufacturer_monthly",
                "load_status": "loaded",
            },
            {
                "source_id": "SRC003",
                "file_name": NEV_OVERALL_FILE.name,
                "topic": "新能源汽车总体产销",
                "time_grain": "month",
                "raw_format": "xlsx",
                "target_table": "fact_nev_overall_monthly",
                "load_status": "loaded",
            },
            {
                "source_id": "SRC004",
                "file_name": CHARGING_FILE.name,
                "topic": "国内充电设施数量",
                "time_grain": "month",
                "raw_format": "xls",
                "target_table": "fact_charging_infrastructure_monthly",
                "load_status": "loaded",
            },
            {
                "source_id": "SRC005",
                "file_name": BATTERY_VEHICLE_FILE.name,
                "topic": "动力电池装车量分车型",
                "time_grain": "month",
                "raw_format": "xls",
                "target_table": "fact_battery_installation_monthly",
                "load_status": "loaded",
            },
            {
                "source_id": "SRC006",
                "file_name": BATTERY_MATERIAL_FILE.name,
                "topic": "动力电池装车量分材料类型",
                "time_grain": "month",
                "raw_format": "xls",
                "target_table": "fact_battery_installation_monthly",
                "load_status": "loaded",
            },
        ]
    )


# ────────────────────────────── 主函数 ──────────────────────────────

def clean_all() -> dict[str, int]:
    """
    执行全部清洗流程，将结果写入 data/cleaned/ 目录

    返回 {表名: 行数} 字典
    """
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    tables = {
        "dim_data_source": build_data_source_table(),
        "fact_vehicle_prod_sales_monthly": clean_vehicle_prod_sales(),
        "fact_nev_manufacturer_monthly": clean_nev_manufacturer(),
        "fact_nev_overall_monthly": clean_nev_overall(),
        "fact_charging_infrastructure_monthly": clean_charging_infrastructure(),
        "fact_battery_installation_monthly": clean_battery_installation(),
    }

    result = {}
    for name, df in tables.items():
        csv_path = CLEANED_DIR / f"{name}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        result[name] = len(df)
        print(f"  ✅ {name} → {csv_path.name} ({len(df)} 行)")

    return result


# ────────────────────────────── 维度表生成：额外原始文件路径 ──────────────────────────────

PROVINCE_PROD_FILE = RAW_DATA_DIR / "32汽车产量统计分省（月，200204-202212，112个指标，不是新能源汽车产量，是所有汽车产量总和）.xls"
BATTERY_PROD_MATERIAL_FILE = RAW_DATA_DIR / "14动力电池产量分材料类型（月，201901-202301，10个指标）.xls"
CHARGING_OPERATOR_FILE = RAW_DATA_DIR / "12公共充电桩运营商充电电量（21家运营商，月，202012-202301）.xls"


# ────────────────────────────── DIM: dim_time ──────────────────────────────

def generate_dim_time() -> pd.DataFrame:
    """
    从所有事实表CSV中提取所有不重复的 data_month，生成时间维度表。

    字段：data_month, year, quarter, month_num, month_name, is_year_end
    """
    print("  生成 dim_time...")

    fact_files = [
        "fact_vehicle_prod_sales_monthly.csv",
        "fact_nev_manufacturer_monthly.csv",
        "fact_nev_overall_monthly.csv",
        "fact_charging_infrastructure_monthly.csv",
        "fact_battery_installation_monthly.csv",
    ]

    all_months = set()
    for f in fact_files:
        csv_path = CLEANED_DIR / f
        if csv_path.exists():
            df = pd.read_csv(csv_path, usecols=["data_month"])
            all_months.update(df["data_month"].dropna().unique())

    month_name_map = {
        1: "一月", 2: "二月", 3: "三月", 4: "四月",
        5: "五月", 6: "六月", 7: "七月", 8: "八月",
        9: "九月", 10: "十月", 11: "十一月", 12: "十二月",
    }

    dates = sorted(all_months)
    rows = []
    for d in dates:
        dt = pd.Timestamp(d)
        rows.append({
            "data_month": d,
            "year": dt.year,
            "quarter": dt.quarter,
            "month_num": dt.month,
            "month_name": month_name_map[dt.month],
            "is_year_end": dt.month == 12,
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 年份范围: {result['year'].min()}-{result['year'].max()}")
    return result


# ────────────────────────────── DIM: dim_manufacturer ──────────────────────────────

# 品牌集团映射表
_BRAND_GROUP_MAP = {
    "特斯拉(上海)": "特斯拉", "特斯拉(上海)公司": "特斯拉", "特斯拉（上海）公司": "特斯拉",
    "比亚迪": "比亚迪", "比亚迪汽车公司": "比亚迪", "比亚迪汽车工业公司": "比亚迪",
    "比亚迪股份公司": "比亚迪", "比亚迪股份公司(集团)": "比亚迪",
    "华晨宝马": "宝马", "华晨宝马汽车公司": "宝马", "宝马": "宝马",
    "一汽丰田": "丰田", "广汽丰田": "丰田", "广汽丰田汽车公司": "丰田",
    "一汽大众": "大众", "上汽大众": "大众",
    "上汽通用": "通用", "上汽通用五菱": "通用",
    "广汽本田": "本田", "广汽本田汽车公司": "本田",
    "北京奔驰": "奔驰", "北京奔驰汽车公司": "奔驰",
    "长城": "长城", "长城汽车股份公司": "长城", "长城汽车股份公司(集团)": "长城",
    "长安": "长安", "重庆长安汽车股份公司": "长安", "中国长安汽车集团公司": "长安",
    "长安福特": "福特",
    "吉利": "吉利", "浙江吉利控股集团公司": "吉利", "浙江吉利控股集团公司(集团)": "吉利",
    "奇瑞": "奇瑞", "奇瑞汽车股份公司": "奇瑞", "奇瑞汽车股份公司(集团)": "奇瑞",
    "广汽乘用车": "广汽", "广汽乘用车公司": "广汽", "广州汽车集团乘用车公司": "广汽",
    "广州汽车工业集团公司": "广汽",
    "北汽股份": "北汽", "北汽新能源": "北汽", "北汽有限": "北汽",
    "北京汽车股份公司": "北汽", "北京汽车集团公司": "北汽", "北京新能源汽车股份公司": "北汽",
    "北汽蓝谷麦格纳": "北汽", "北汽蓝谷麦格纳汽车公司": "北汽",
    "北汽(广州)": "北汽", "北汽(广州)汽车公司": "北汽",
    "北汽新能源(常州)": "北汽", "北汽新能源汽车常州公司": "北汽",
    "北汽(常州)汽车公司": "北汽", "北汽（常州）汽车公司": "北汽", "北汽（镇江）汽车公司": "北汽",
    "北汽福田汽车股份公司": "北汽", "福田": "北汽",
    "东风": "东风", "东风本田": "东风", "东风日产": "东风", "东风乘用车": "东风",
    "东风启辰": "东风", "东风柳汽": "东风", "东风悦达": "东风", "东风股份": "东风",
    "东风神龙": "东风", "东风裕隆": "东风",
    "东风汽车集团股份公司": "东风", "东风汽车股份公司": "东风",
    "东风汽车集团公司": "东风", "东风裕隆汽车公司": "东风",
    "重庆理想": "理想", "重庆理想汽车公司": "理想", "重庆理想汽车公司(集团)": "理想",
    "肇庆小鹏": "小鹏", "肇庆小鹏汽车公司": "小鹏",
    "威马": "威马", "威马汽车": "威马", "威马汽车制造温州公司": "威马",
    "浙江零跑": "零跑", "浙江零跑科技公司": "零跑",
    "合众新能源": "哪吒", "浙江合众新能源汽车公司": "哪吒",
    "岚图汽车": "岚图", "岚图汽车科技公司": "岚图",
    "赛力斯汽车": "赛力斯", "赛力斯汽车公司": "赛力斯", "重庆金康新能源汽车公司": "赛力斯",
    "飞凡科技": "飞凡", "飞凡汽车科技公司": "飞凡",
    "江淮": "江淮", "安徽江淮汽车集团股份公司": "江淮", "安徽江淮汽车集团股份公司(集团)": "江淮",
    "江铃股份": "江铃", "江铃控股": "江铃", "江铃新能源": "江铃", "江铃控股公司": "江铃",
    "华晨": "华晨", "华晨汽车集团控股公司": "华晨", "华晨汽车集团控股公司(集团)": "华晨",
    "华晨鑫源": "华晨", "华晨鑫源重庆汽车公司": "华晨",
    "华晨新日": "华晨", "华晨新日新能源汽车公司": "华晨",
    "华晨雷诺金杯": "华晨",
    "中国一汽": "一汽", "中国第一汽车集团公司": "一汽", "中国第一汽车集团公司(集团)": "一汽",
    "天津一汽": "一汽",
    "上海股份": "上汽", "上汽通用五菱": "上汽",
    "北京现代": "现代", "北京现代汽车公司": "现代",
    "捷豹路虎": "捷豹路虎", "奇瑞捷豹路虎汽车公司": "捷豹路虎",
    "大庆沃尔沃": "沃尔沃", "大庆沃尔沃汽车制造公司": "沃尔沃",
    "长安马自达": "马自达",
    "广汽三菱": "三菱", "广汽三菱汽车公司": "三菱",
    "广汽菲克": "菲亚特克莱斯勒", "广汽菲亚特克莱斯勒汽车公司": "菲亚特克莱斯勒",
    "郑州日产": "日产", "郑州日产汽车公司": "日产",
    "神龙汽车公司": "标致雪铁龙", "东风神龙": "标致雪铁龙",
}

# 国别映射表
_COUNTRY_MAP = {
    "特斯拉": "美国", "福特": "美国", "通用": "美国", "菲亚特克莱斯勒": "美国",
    "宝马": "德国", "奔驰": "德国", "大众": "德国",
    "丰田": "日本", "本田": "日本", "日产": "日本", "马自达": "日本", "三菱": "日本",
    "现代": "韩国",
    "沃尔沃": "瑞典",
    "捷豹路虎": "英国",
    "标致雪铁龙": "法国",
}


def generate_dim_manufacturer() -> pd.DataFrame:
    """
    从 fact_vehicle_prod_sales_monthly.csv 和 fact_nev_manufacturer_monthly.csv
    中提取所有不重复的 manufacturer_name，生成厂商维度表。

    字段：manufacturer_id, manufacturer_name, brand_group, is_nev, country
    """
    print("  生成 dim_manufacturer...")

    veh_path = CLEANED_DIR / "fact_vehicle_prod_sales_monthly.csv"
    nev_path = CLEANED_DIR / "fact_nev_manufacturer_monthly.csv"

    veh_mfrs = set()
    nev_mfrs = set()

    if veh_path.exists():
        df = pd.read_csv(veh_path, usecols=["manufacturer_name"])
        veh_mfrs = set(df["manufacturer_name"].dropna().unique())

    if nev_path.exists():
        df = pd.read_csv(nev_path, usecols=["manufacturer_name"])
        nev_mfrs = set(df["manufacturer_name"].dropna().unique())

    all_mfrs = sorted(veh_mfrs | nev_mfrs)

    rows = []
    for i, name in enumerate(all_mfrs, 1):
        brand_group = _BRAND_GROUP_MAP.get(name, "其他")
        is_nev = name in nev_mfrs
        country = _COUNTRY_MAP.get(brand_group, "中国")
        rows.append({
            "manufacturer_id": f"MFR{i:06d}",
            "manufacturer_name": name,
            "brand_group": brand_group,
            "is_nev": is_nev,
            "country": country,
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 品牌集团数: {result['brand_group'].nunique()}")
    return result


# ────────────────────────────── DIM: dim_vehicle_model ──────────────────────────────

def generate_dim_vehicle_model() -> pd.DataFrame:
    """
    从 fact_vehicle_prod_sales_monthly.csv 中提取所有不重复的
    model_name + manufacturer_name 组合，生成车型维度表。

    字段：model_id, model_name, manufacturer_name, vehicle_category, fuel_type
    """
    print("  生成 dim_vehicle_model...")

    csv_path = CLEANED_DIR / "fact_vehicle_prod_sales_monthly.csv"
    df = pd.read_csv(csv_path, usecols=["model_name", "manufacturer_name", "vehicle_category"])

    # 取每个 (model_name, manufacturer_name) 组合中最常出现的 vehicle_category
    mode_cat = (
        df.groupby(["model_name", "manufacturer_name"])["vehicle_category"]
        .agg(lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else x.iloc[0])
        .reset_index()
    )

    # 推断燃料类型
    def infer_fuel_type(model_name: str) -> str:
        if "BEV" in model_name:
            return "纯电动"
        elif "PHEV" in model_name:
            return "插电式混合动力"
        else:
            return "传统燃油"

    mode_cat = mode_cat.sort_values(["manufacturer_name", "model_name"]).reset_index(drop=True)

    rows = []
    for i, row in enumerate(mode_cat.itertuples(), 1):
        rows.append({
            "model_id": f"MDL{i:06d}",
            "model_name": row.model_name,
            "manufacturer_name": row.manufacturer_name,
            "vehicle_category": row.vehicle_category,
            "fuel_type": infer_fuel_type(row.model_name),
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 燃料类型分布: {result['fuel_type'].value_counts().to_dict()}")
    return result


# ────────────────────────────── DIM: dim_province ──────────────────────────────

# 大区映射表
_REGION_MAP = {
    "北京": "华北", "天津": "华北", "河北": "华北", "山西": "华北", "内蒙古": "华北",
    "辽宁": "东北", "吉林": "东北", "黑龙江": "东北",
    "上海": "华东", "江苏": "华东", "浙江": "华东", "安徽": "华东",
    "福建": "华东", "江西": "华东", "山东": "华东",
    "河南": "华中", "湖北": "华中", "湖南": "华中",
    "广东": "华南", "广西": "华南", "海南": "华南",
    "重庆": "西南", "四川": "西南", "贵州": "西南", "云南": "西南", "西藏": "西南",
    "陕西": "西北", "甘肃": "西北", "青海": "西北", "宁夏": "西北", "新疆": "西北",
    "台湾": "华东", "香港": "华南", "澳门": "华南",
}

# 省份等级映射
_TIER_MAP = {
    "北京": "直辖市", "天津": "直辖市", "上海": "直辖市", "重庆": "直辖市",
    "内蒙古": "自治区", "广西": "自治区", "西藏": "自治区", "宁夏": "自治区", "新疆": "自治区",
    "香港": "特别行政区", "澳门": "特别行政区",
}


def generate_dim_province() -> pd.DataFrame:
    """
    从 fact_charging_infrastructure_monthly.csv 和 32号文件列名中
    提取所有不重复的省份，生成省份维度表。

    字段：province_code, province, region, tier
    """
    print("  生成 dim_province...")

    provinces = set()

    # 从充电设施 CSV 中提取
    chg_path = CLEANED_DIR / "fact_charging_infrastructure_monthly.csv"
    if chg_path.exists():
        df = pd.read_csv(chg_path, usecols=["province"])
        for p in df["province"].dropna().unique():
            if p != "全国":
                provinces.add(p)

    # 从 32号文件列名中提取省份
    if PROVINCE_PROD_FILE.exists():
        raw = pd.read_excel(PROVINCE_PROD_FILE, header=None)
        cols = raw.iloc[1, 1:].tolist()
        for c in cols:
            if isinstance(c, str):
                parts = c.split("_")
                if len(parts) >= 3:
                    provinces.add(parts[2])

    sorted_provinces = sorted(provinces)
    rows = []
    for i, prov in enumerate(sorted_provinces, 1):
        rows.append({
            "province_code": f"P{i:02d}",
            "province": prov,
            "region": _REGION_MAP.get(prov, "未知"),
            "tier": _TIER_MAP.get(prov, "省"),
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 大区分布: {result['region'].value_counts().to_dict()}")
    return result


# ────────────────────────────── DIM: dim_fuel_type ──────────────────────────────

# 燃料大类映射
_FUEL_CATEGORY_MAP = {
    "纯电动": "新能源",
    "插电式混合动力": "新能源",
    "燃料电池": "新能源",
    "总计": "汇总",
}


def generate_dim_fuel_type() -> pd.DataFrame:
    """
    从 fact_nev_manufacturer_monthly.csv 和 fact_nev_overall_monthly.csv
    中提取所有不重复的 fuel_type，生成燃料类型维度表。

    字段：fuel_type_id, fuel_type, fuel_category, is_nev
    """
    print("  生成 dim_fuel_type...")

    fuel_types = set()

    for fname in ["fact_nev_manufacturer_monthly.csv", "fact_nev_overall_monthly.csv"]:
        csv_path = CLEANED_DIR / fname
        if csv_path.exists():
            df = pd.read_csv(csv_path, usecols=["fuel_type"])
            fuel_types.update(df["fuel_type"].dropna().unique())

    sorted_fuels = sorted(fuel_types)
    rows = []
    for i, ft in enumerate(sorted_fuels, 1):
        category = _FUEL_CATEGORY_MAP.get(ft, "传统")
        rows.append({
            "fuel_type_id": f"FT{i:02d}",
            "fuel_type": ft,
            "fuel_category": category,
            "is_nev": category == "新能源",
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 类型: {result['fuel_type'].tolist()}")
    return result


# ────────────────────────────── DIM: dim_battery_material ──────────────────────────────

# 材料大类映射
_MATERIAL_CATEGORY_MAP = {
    "三元材料": "三元系",
    "磷酸铁锂": "磷酸铁锂系",
    "锰酸锂": "其他",
    "钛酸锂": "其他",
    "合计": "汇总",
}


def generate_dim_battery_material() -> pd.DataFrame:
    """
    从 fact_battery_installation_monthly.csv（dimension_type='material_type'）
    和 14号文件列名中提取所有不重复的材料名，生成电池材料维度表。

    字段：material_id, material_name, material_category
    """
    print("  生成 dim_battery_material...")

    materials = set()

    # 从事实表 CSV 提取
    bat_path = CLEANED_DIR / "fact_battery_installation_monthly.csv"
    if bat_path.exists():
        df = pd.read_csv(bat_path)
        mat_df = df[df["dimension_type"] == "material_type"]
        materials.update(mat_df["dimension_value"].dropna().unique())

    # 从 14号文件列名中提取
    if BATTERY_PROD_MATERIAL_FILE.exists():
        raw = pd.read_excel(BATTERY_PROD_MATERIAL_FILE, header=None)
        cols = raw.iloc[1, 1:].tolist()
        for c in cols:
            if isinstance(c, str):
                parts = c.split("_")
                if len(parts) >= 3:
                    materials.add(parts[2])

    sorted_materials = sorted(materials)
    rows = []
    for i, mat in enumerate(sorted_materials, 1):
        rows.append({
            "material_id": f"MAT{i:02d}",
            "material_name": mat,
            "material_category": _MATERIAL_CATEGORY_MAP.get(mat, "其他"),
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 材料: {result['material_name'].tolist()}")
    return result


# ────────────────────────────── DIM: dim_charging_operator ──────────────────────────────

# 运营商类型映射
_OPERATOR_TYPE_MAP = {
    "特来电": "民营企业",
    "星星充电": "民营企业",
    "云快充": "民营企业",
    "南方电网": "国有企业",
    "思极星能": "国有企业",
}


def generate_dim_charging_operator() -> pd.DataFrame:
    """
    从 12号文件列名中提取运营商名称，生成充电运营商维度表。

    列名格式：公共充电桩运营商充电电量_运营商名称

    字段：operator_id, operator_name, operator_type
    """
    print("  生成 dim_charging_operator...")

    operators = []

    if CHARGING_OPERATOR_FILE.exists():
        raw = pd.read_excel(CHARGING_OPERATOR_FILE, header=None)
        cols = raw.iloc[1, 1:].tolist()
        for c in cols:
            if isinstance(c, str) and "_" in c:
                name = c.split("_", 1)[1]  # 取第一个 _ 后面的部分
                operators.append(name)

    # 去重并排序
    operators = sorted(set(operators))

    rows = []
    for i, name in enumerate(operators, 1):
        rows.append({
            "operator_id": f"OPR{i:02d}",
            "operator_name": name,
            "operator_type": _OPERATOR_TYPE_MAP.get(name, "民营企业"),
        })

    result = pd.DataFrame(rows)
    print(f"    行数: {len(result)}, 国有: {sum(1 for r in rows if r['operator_type'] == '国有企业')}, "
          f"民营: {sum(1 for r in rows if r['operator_type'] == '民营企业')}")
    return result


# ────────────────────────────── 维度表生成主函数 ──────────────────────────────

def generate_all_dimensions() -> dict[str, int]:
    """
    执行全部维度表生成流程，将结果写入 data/cleaned/ 目录

    返回 {表名: 行数} 字典
    """
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    dim_tables = {
        "dim_time": generate_dim_time(),
        "dim_manufacturer": generate_dim_manufacturer(),
        "dim_vehicle_model": generate_dim_vehicle_model(),
        "dim_province": generate_dim_province(),
        "dim_fuel_type": generate_dim_fuel_type(),
        "dim_battery_material": generate_dim_battery_material(),
        "dim_charging_operator": generate_dim_charging_operator(),
    }

    result = {}
    for name, df in dim_tables.items():
        csv_path = CLEANED_DIR / f"{name}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        result[name] = len(df)
        print(f"  ✅ {name} → {csv_path.name} ({len(df)} 行)")

    return result


if __name__ == "__main__":
    print("开始清洗原始 Excel 数据...\n")
    counts = clean_all()
    print(f"\n清洗完成，共 {sum(counts.values())} 行数据写入 {CLEANED_DIR}")

    print("\n开始生成维度表...\n")
    dim_counts = generate_all_dimensions()
    print(f"\n维度表生成完成，共 {sum(dim_counts.values())} 行数据写入 {CLEANED_DIR}")
