"""
build_duckdb.py — CSV 入库脚本（CSV → DuckDB）

读取 data/cleaned/ 下的 6 个清洗后 CSV 文件，建表并写入 DuckDB 数据库。
本脚本不包含任何清洗逻辑，仅负责「干净数据 → 数据库」的最后一步。

前置步骤：
    python scripts/clean_raw_data.py    # 先生成 data/cleaned/*.csv

使用方法：
    python scripts/build_duckdb.py

产出：
    data/autobi.duckdb
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


# ────────────────────────────── 路径常量 ──────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "autobi.duckdb"

# 需要入库的表清单（CSV 文件名 = 表名）
TABLE_NAMES = [
    "dim_data_source",
    "fact_vehicle_prod_sales_monthly",
    "fact_nev_manufacturer_monthly",
    "fact_nev_overall_monthly",
    "fact_charging_infrastructure_monthly",
    "fact_battery_installation_monthly",
]


# ────────────────────────────── 核心函数 ──────────────────────────────

def build_database(db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, int]:
    """
    从 data/cleaned/ 读取 CSV 文件，写入 DuckDB 数据库。

    参数：
        db_path: DuckDB 数据库文件路径，默认为 data/autobi.duckdb

    返回：
        {表名: 行数} 字典
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 每次重新生成，先删除旧库
    if db_path.exists():
        db_path.unlink()

    counts: dict[str, int] = {}

    with duckdb.connect(str(db_path)) as conn:
        for table_name in TABLE_NAMES:
            csv_path = CLEANED_DIR / f"{table_name}.csv"
            if not csv_path.exists():
                print(f"  ⚠️ 跳过 {table_name}: {csv_path} 不存在")
                continue

            df = pd.read_csv(csv_path)

            # 注册 DataFrame 为临时视图，再通过 SQL 建表
            conn.register("_df", df)
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM _df")
            conn.unregister("_df")

            counts[table_name] = len(df)
            print(f"  ✅ {table_name}: {len(df)} 行")

    return counts


# ────────────────────────────── 主函数 ──────────────────────────────

if __name__ == "__main__":
    print(f"从 {CLEANED_DIR} 读取 CSV 并写入 DuckDB...\n")

    counts = build_database()

    print(f"\n入库完成: {DEFAULT_DB_PATH}")
    print(f"共 {len(counts)} 张表, {sum(counts.values())} 行数据")
