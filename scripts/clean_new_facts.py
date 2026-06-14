"""
clean_new_facts.py — 5 张新事实表的清洗脚本（Excel → CSV）

读取 data/raw_data/ 下的 7 个 Datayes 格式原始文件，执行宽表转长表、
字段映射、单位统一和标准化，输出干净的 CSV 文件至 data/cleaned/ 目录。

原始文件统一格式（Datayes 平台）：
  - 第 0 行: 'Datayes!'
  - 第 1 行: 指标名称（列头）
  - 第 2 行: 频度
  - 第 3 行: 单位
  - 第 4 行: 来源
  - 第 5 行: 更新时间
  - 第 6 行起: 实际数据（第一列日期，后续列为指标值）

清洗产出：
    data/cleaned/fact_global_ev_sales_yearly.csv       (SRC007 + SRC008)
    data/cleaned/fact_global_ev_stock_yearly.csv       (SRC009 + SRC010)
    data/cleaned/fact_battery_production_monthly.csv   (SRC011)
    data/cleaned/fact_vehicle_production_province_monthly.csv  (SRC012)
    data/cleaned/fact_charging_operator_monthly.csv    (SRC013)

同时追加更新 dim_data_source.csv（SRC007 ~ SRC013）

使用方法：
    python scripts/clean_new_facts.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


# ────────────────────────────── 路径常量 ──────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"

# 全球 EV 销量
EV_SALES_BEV_FILE = RAW_DATA_DIR / "5全球电动汽车新车销量（20个国家，纯电动汽车，2005-2021）.xls"
EV_SALES_PHEV_FILE = RAW_DATA_DIR / "6全球电动汽车新车销量（20个国家，插电式混合动力，2009-2021）.xls"

# 全球 EV 保有量
EV_STOCK_PHEV_FILE = RAW_DATA_DIR / "7全球电动汽车保有量（20个国家，插电式混合动力汽车，2009-2021）.xls"
EV_STOCK_BEV_FILE = RAW_DATA_DIR / "8全球电动汽车保有量（20个国家，纯电动汽车，2005-2021）.xls"

# 动力电池产量
BATTERY_PROD_FILE = RAW_DATA_DIR / "14动力电池产量分材料类型（月，201901-202301，10个指标）.xls"

# 汽车产量分省
VEHICLE_PROVINCE_FILE = RAW_DATA_DIR / "32汽车产量统计分省（月，200204-202212，112个指标，不是新能源汽车产量，是所有汽车产量总和）.xls"

# 充电桩运营商
CHARGING_OPERATOR_FILE = RAW_DATA_DIR / "12公共充电桩运营商充电电量（21家运营商，月，202012-202301）.xls"


# ────────────────────────────── 通用工具函数 ──────────────────────────────

def _to_number(series: pd.Series) -> pd.Series:
    """将 Series 强制转换为数值类型，无法转换的变为 NaN"""
    return pd.to_numeric(series, errors="coerce")


def _to_date(series: pd.Series) -> pd.Series:
    """将 Series 转换为日期类型，只保留日期部分"""
    return pd.to_datetime(series, errors="coerce").dt.date


def _with_record_id(df: pd.DataFrame, prefix: str) -> list[str]:
    """生成带有特定前缀的定长自增记录 ID，例如 'GES000001'"""
    return [f"{prefix}{i:06d}" for i in range(1, len(df) + 1)]


def _read_datayes_wide(file_path: Path) -> tuple[pd.DataFrame, list[str], dict[str, str]]:
    """
    读取 Datayes 宽表格式文件，返回 (数据部分 DataFrame, 指标名列表, 指标→单位映射)

    Datayes 格式：
      row 0: 'Datayes!' 标记
      row 1: 指标名称
      row 2: 频度
      row 3: 单位
      row 4: 来源
      row 5: 更新时间
      row 6+: 实际数据
    """
    raw = pd.read_excel(file_path, header=None)
    metrics = raw.iloc[1, 1:].tolist()
    units = raw.iloc[3, 1:].tolist()
    unit_map = dict(zip(metrics, units))

    data = raw.iloc[6:].copy()
    data.columns = ["date"] + metrics

    # 过滤掉日期列为空的尾部行
    data = data.dropna(subset=["date"])

    return data, metrics, unit_map


# GWh → MWh 换算系数
GWH_TO_MWH = 1000.0


# ────────────────────────────── SRC007 + SRC008: 全球 EV 销量 ──────────────────────────────

# ev_type 列名中文标准化映射
_EV_TYPE_MAP = {
    "纯电动汽车": "纯电动",
    "插电式混合动力汽车": "插电式混合动力",
}


def _parse_ev_global_file(
    file_path: Path,
    source_id: str,
    value_col_name: str,
) -> pd.DataFrame:
    """
    通用解析全球 EV 销量/保有量宽表

    列名格式：
      '销量_纯电动汽车_中国' → ev_type='纯电动', country='中国'
      '保有量_插电式混合动力汽车_合计' → ev_type='插电式混合动力', country='合计'

    参数:
      value_col_name: 输出中的数值列名（'sales_volume' 或 'stock_volume'）
    """
    data, metrics, unit_map = _read_datayes_wide(file_path)

    parsed_rows = []
    for metric_name in metrics:
        if not isinstance(metric_name, str):
            continue

        parts = metric_name.split("_")
        if len(parts) < 3:
            continue

        # parts[0] = '销量'/'保有量', parts[1] = EV类型, parts[2] = 国家
        raw_ev_type = parts[1]
        country = parts[2]

        ev_type = _EV_TYPE_MAP.get(raw_ev_type, raw_ev_type)
        unit = str(unit_map.get(metric_name, "千辆"))

        for _, row in data.iterrows():
            parsed_rows.append(
                {
                    "source_id": source_id,
                    "country": country,
                    "ev_type": ev_type,
                    "data_year": row["date"],
                    value_col_name: row[metric_name],
                    "unit": unit,
                }
            )

    df = pd.DataFrame(parsed_rows)
    df["data_year"] = pd.to_datetime(df["data_year"], errors="coerce").dt.year
    df[value_col_name] = _to_number(df[value_col_name])
    df = df.dropna(subset=["data_year"])
    df["data_year"] = df["data_year"].astype(int)

    return df


def clean_global_ev_sales() -> pd.DataFrame:
    """
    清洗 SRC007 + SRC008: 全球电动汽车新车销量

    - SRC007: 纯电动汽车（20 国，2005-2021）
    - SRC008: 插电式混合动力（20 国，2009-2021）
    - 过滤掉 country='合计' 的行（可计算得出）
    """
    print("  清洗 SRC007 + SRC008: 全球电动汽车新车销量...")

    df_bev = _parse_ev_global_file(EV_SALES_BEV_FILE, "SRC007", "sales_volume")
    df_phev = _parse_ev_global_file(EV_SALES_PHEV_FILE, "SRC008", "sales_volume")

    df = pd.concat([df_bev, df_phev], ignore_index=True)

    # 过滤合计行
    before = len(df)
    df = df[df["country"] != "合计"].copy()
    print(f"    过滤合计行: {before} → {len(df)} (移除 {before - len(df)} 行)")

    df["record_id"] = _with_record_id(df, "GES")
    df = df[["record_id", "source_id", "country", "ev_type", "data_year", "sales_volume", "unit"]]

    print(f"    行数: {len(df)}, ev_type: {df['ev_type'].unique().tolist()}")
    print(f"    国家数: {df['country'].nunique()}, 年份范围: {df['data_year'].min()}-{df['data_year'].max()}")
    return df


# ────────────────────────────── SRC009 + SRC010: 全球 EV 保有量 ──────────────────────────────

def clean_global_ev_stock() -> pd.DataFrame:
    """
    清洗 SRC009 + SRC010: 全球电动汽车保有量

    - SRC009: 插电式混合动力（20 国，2009-2021）
    - SRC010: 纯电动汽车（20 国，2005-2021）
    - 过滤掉 country='合计' 的行
    """
    print("  清洗 SRC009 + SRC010: 全球电动汽车保有量...")

    df_phev = _parse_ev_global_file(EV_STOCK_PHEV_FILE, "SRC009", "stock_volume")
    df_bev = _parse_ev_global_file(EV_STOCK_BEV_FILE, "SRC010", "stock_volume")

    df = pd.concat([df_phev, df_bev], ignore_index=True)

    # 过滤合计行
    before = len(df)
    df = df[df["country"] != "合计"].copy()
    print(f"    过滤合计行: {before} → {len(df)} (移除 {before - len(df)} 行)")

    df["record_id"] = _with_record_id(df, "GST")
    df = df[["record_id", "source_id", "country", "ev_type", "data_year", "stock_volume", "unit"]]

    print(f"    行数: {len(df)}, ev_type: {df['ev_type'].unique().tolist()}")
    print(f"    国家数: {df['country'].nunique()}, 年份范围: {df['data_year'].min()}-{df['data_year'].max()}")
    return df


# ────────────────────────────── SRC011: 动力电池产量 ──────────────────────────────

def clean_battery_production() -> pd.DataFrame:
    """
    清洗 SRC011: 动力电池产量分材料类型

    列名格式：'产量_动力电池_合计_当期值' → material_type='合计', metric_name='当期值'

    单位处理：
    - 合计列使用 GWh，需乘以 1000 转为 MWh
    - 其他材料类型列已经是 MWh
    """
    print("  清洗 SRC011: 动力电池产量分材料类型...")
    data, metrics, unit_map = _read_datayes_wide(BATTERY_PROD_FILE)

    parsed_rows = []
    for metric_name in metrics:
        if not isinstance(metric_name, str):
            continue

        parts = metric_name.split("_")
        if len(parts) < 4:
            continue

        # parts: ['产量', '动力电池', '材料类型', '当期值/累计值']
        material_type = parts[2]
        stat_type = parts[3]  # 当期值 / 累计值

        raw_unit = str(unit_map.get(metric_name, ""))

        for _, row in data.iterrows():
            value = row[metric_name]

            # 统一单位：GWh → MWh
            if raw_unit == "GWh" and pd.notna(value):
                value = value * GWH_TO_MWH

            parsed_rows.append(
                {
                    "source_id": "SRC011",
                    "material_type": material_type,
                    "data_month": row["date"],
                    "metric_name": stat_type,
                    "metric_value": value,
                    "unit": "MWh",
                }
            )

    df = pd.DataFrame(parsed_rows)
    df["data_month"] = _to_date(df["data_month"])
    df["metric_value"] = _to_number(df["metric_value"])
    df = df.dropna(subset=["data_month"]).copy()

    df["record_id"] = _with_record_id(df, "BPR")
    df = df[["record_id", "source_id", "material_type", "data_month", "metric_name", "metric_value", "unit"]]

    print(f"    行数: {len(df)}, 材料类型: {df['material_type'].unique().tolist()}")
    print(f"    指标: {df['metric_name'].unique().tolist()}")
    # 验证单位统一
    print(f"    单位分布: {df['unit'].value_counts().to_dict()}")
    return df


# ────────────────────────────── SRC012: 汽车产量分省 ──────────────────────────────

# 指标类型 → 单位映射
_PROVINCE_METRIC_UNIT = {
    "当月值": "万辆",
    "当月同比": "%",
    "累计值": "万辆",
    "累计同比": "%",
}


def clean_vehicle_production_province() -> pd.DataFrame:
    """
    清洗 SRC012: 汽车产量统计分省

    列名格式：'产量_汽车_北京_当月值' → province='北京', metric_name='当月值'
    4 种指标：当月值、当月同比、累计值、累计同比
    单位：万辆（绝对值指标）或 %（同比指标）
    """
    print("  清洗 SRC012: 汽车产量统计分省...")
    data, metrics, unit_map = _read_datayes_wide(VEHICLE_PROVINCE_FILE)

    parsed_rows = []
    for metric_name in metrics:
        if not isinstance(metric_name, str):
            continue

        parts = metric_name.split("_")
        if len(parts) < 4:
            continue

        # parts: ['产量', '汽车', '省份', '当月值/当月同比/累计值/累计同比']
        province = parts[2]
        stat_type = parts[3]
        unit = _PROVINCE_METRIC_UNIT.get(stat_type, unit_map.get(metric_name, ""))

        for _, row in data.iterrows():
            parsed_rows.append(
                {
                    "source_id": "SRC012",
                    "province": province,
                    "data_month": row["date"],
                    "metric_name": stat_type,
                    "metric_value": row[metric_name],
                    "unit": unit,
                }
            )

    df = pd.DataFrame(parsed_rows)
    df["data_month"] = _to_date(df["data_month"])
    df["metric_value"] = _to_number(df["metric_value"])
    df = df.dropna(subset=["data_month"]).copy()

    df["record_id"] = _with_record_id(df, "VPP")
    df = df[["record_id", "source_id", "province", "data_month", "metric_name", "metric_value", "unit"]]

    print(f"    行数: {len(df)}, 省份数: {df['province'].nunique()}")
    print(f"    指标: {df['metric_name'].unique().tolist()}")
    print(f"    单位分布: {df['unit'].value_counts().to_dict()}")
    return df


# ────────────────────────────── SRC013: 充电桩运营商 ──────────────────────────────

def clean_charging_operator() -> pd.DataFrame:
    """
    清洗 SRC013: 公共充电桩运营商充电电量

    列名格式：'公共充电桩运营商充电电量_特来电' → operator_name='特来电'
    """
    print("  清洗 SRC013: 公共充电桩运营商充电电量...")
    data, metrics, unit_map = _read_datayes_wide(CHARGING_OPERATOR_FILE)

    parsed_rows = []
    for metric_name in metrics:
        if not isinstance(metric_name, str):
            continue

        parts = metric_name.split("_")
        if len(parts) < 2:
            continue

        # parts: ['公共充电桩运营商充电电量', '运营商名']
        operator_name = parts[-1]

        for _, row in data.iterrows():
            parsed_rows.append(
                {
                    "source_id": "SRC013",
                    "operator_name": operator_name,
                    "data_month": row["date"],
                    "charging_volume": row[metric_name],
                    "unit": "万度",
                }
            )

    df = pd.DataFrame(parsed_rows)
    df["data_month"] = _to_date(df["data_month"])
    df["charging_volume"] = _to_number(df["charging_volume"])
    df = df.dropna(subset=["data_month"]).copy()

    df["record_id"] = _with_record_id(df, "COP")
    df = df[["record_id", "source_id", "operator_name", "data_month", "charging_volume", "unit"]]

    print(f"    行数: {len(df)}, 运营商数: {df['operator_name'].nunique()}")
    print(f"    运营商: {sorted(df['operator_name'].unique().tolist())}")
    return df


# ────────────────────────────── 更新 dim_data_source ──────────────────────────────

NEW_SOURCES = [
    {
        "source_id": "SRC007",
        "file_name": EV_SALES_BEV_FILE.name,
        "topic": "全球电动汽车新车销量(纯电动)",
        "time_grain": "year",
        "raw_format": "xls",
        "target_table": "fact_global_ev_sales_yearly",
        "load_status": "loaded",
    },
    {
        "source_id": "SRC008",
        "file_name": EV_SALES_PHEV_FILE.name,
        "topic": "全球电动汽车新车销量(插混)",
        "time_grain": "year",
        "raw_format": "xls",
        "target_table": "fact_global_ev_sales_yearly",
        "load_status": "loaded",
    },
    {
        "source_id": "SRC009",
        "file_name": EV_STOCK_PHEV_FILE.name,
        "topic": "全球电动汽车保有量(插混)",
        "time_grain": "year",
        "raw_format": "xls",
        "target_table": "fact_global_ev_stock_yearly",
        "load_status": "loaded",
    },
    {
        "source_id": "SRC010",
        "file_name": EV_STOCK_BEV_FILE.name,
        "topic": "全球电动汽车保有量(纯电动)",
        "time_grain": "year",
        "raw_format": "xls",
        "target_table": "fact_global_ev_stock_yearly",
        "load_status": "loaded",
    },
    {
        "source_id": "SRC011",
        "file_name": BATTERY_PROD_FILE.name,
        "topic": "动力电池产量分材料类型",
        "time_grain": "month",
        "raw_format": "xls",
        "target_table": "fact_battery_production_monthly",
        "load_status": "loaded",
    },
    {
        "source_id": "SRC012",
        "file_name": VEHICLE_PROVINCE_FILE.name,
        "topic": "汽车产量统计分省",
        "time_grain": "month",
        "raw_format": "xls",
        "target_table": "fact_vehicle_production_province_monthly",
        "load_status": "loaded",
    },
    {
        "source_id": "SRC013",
        "file_name": CHARGING_OPERATOR_FILE.name,
        "topic": "公共充电桩运营商充电电量",
        "time_grain": "month",
        "raw_format": "xls",
        "target_table": "fact_charging_operator_monthly",
        "load_status": "loaded",
    },
]


def update_data_source_table() -> pd.DataFrame:
    """读取现有 dim_data_source.csv，追加 SRC007-SRC013 记录"""
    csv_path = CLEANED_DIR / "dim_data_source.csv"
    existing = pd.read_csv(csv_path)

    # 移除已有的 SRC007-SRC013（如有），防止重复追加
    new_ids = {s["source_id"] for s in NEW_SOURCES}
    existing = existing[~existing["source_id"].isin(new_ids)]

    new_df = pd.DataFrame(NEW_SOURCES)
    combined = pd.concat([existing, new_df], ignore_index=True)

    return combined


# ────────────────────────────── 主函数 ──────────────────────────────

def clean_all() -> dict[str, int]:
    """
    执行全部清洗流程，将结果写入 data/cleaned/ 目录

    返回 {表名: 行数} 字典
    """
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)

    tables = {
        "fact_global_ev_sales_yearly": clean_global_ev_sales(),
        "fact_global_ev_stock_yearly": clean_global_ev_stock(),
        "fact_battery_production_monthly": clean_battery_production(),
        "fact_vehicle_production_province_monthly": clean_vehicle_production_province(),
        "fact_charging_operator_monthly": clean_charging_operator(),
    }

    result = {}
    for name, df in tables.items():
        csv_path = CLEANED_DIR / f"{name}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        result[name] = len(df)
        print(f"  ✅ {name} → {csv_path.name} ({len(df)} 行)")

    # 更新 dim_data_source
    ds_df = update_data_source_table()
    ds_path = CLEANED_DIR / "dim_data_source.csv"
    ds_df.to_csv(ds_path, index=False, encoding="utf-8-sig")
    result["dim_data_source"] = len(ds_df)
    print(f"  ✅ dim_data_source → {ds_path.name} ({len(ds_df)} 行)")

    return result


if __name__ == "__main__":
    print("开始清洗 5 张新事实表...\n")
    counts = clean_all()
    print(f"\n{'='*60}")
    print("清洗完成汇总:")
    for name, cnt in counts.items():
        print(f"  {name}: {cnt} 行")
    print(f"\n共 {sum(counts.values())} 行数据写入 {CLEANED_DIR}")
