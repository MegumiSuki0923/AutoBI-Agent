"""
build_doris_warehouse.py - Doris 数仓建仓脚本（CSV -> ODS -> DWD -> DWS -> ADS）

读取 data/cleaned/ 下的清洗后 CSV 文件，重建 Doris ODS 表并生成 DWD、DWS、ADS
分层表。本脚本不包含 Excel 清洗逻辑，仅负责「干净数据 -> Doris 数仓」。
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEANED_DIR = PROJECT_ROOT / "data" / "cleaned"

SOURCE_TABLES = [
    # 维度表
    "dim_data_source",
    "dim_time",
    "dim_manufacturer",
    "dim_vehicle_model",
    "dim_province",
    "dim_fuel_type",
    "dim_battery_material",
    "dim_charging_operator",
    # 事实表
    "fact_vehicle_prod_sales_monthly",
    "fact_nev_manufacturer_monthly",
    "fact_nev_overall_monthly",
    "fact_charging_infrastructure_monthly",
    "fact_battery_installation_monthly",
    "fact_global_ev_sales_yearly",
    "fact_global_ev_stock_yearly",
    "fact_battery_production_monthly",
    "fact_vehicle_production_province_monthly",
    "fact_charging_operator_monthly",
]


def build_warehouse(
    *,
    cleaned_dir: Path | str = CLEANED_DIR,
    host: str | None = None,
    query_port: int | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> dict[str, int]:
    """
    从清洗后的 CSV 文件重建 Doris 数仓。

    返回:
        {ODS表名: 行数}
    """
    cleaned_path = Path(cleaned_dir)
    counts: dict[str, int] = {}

    conn_kwargs = {
        "host": host or os.getenv("DORIS_HOST", "127.0.0.1"),
        "port": int(query_port or os.getenv("DORIS_QUERY_PORT", "9030")),
        "user": user or os.getenv("DORIS_USER", "root"),
        "password": password if password is not None else os.getenv("DORIS_PASSWORD", ""),
        "database": database or os.getenv("DORIS_DATABASE", "autobi"),
        "charset": "utf8mb4",
        "autocommit": True,
    }

    with _connect(**conn_kwargs) as conn:
        with conn.cursor() as cursor:
            for source_table in SOURCE_TABLES:
                csv_path = cleaned_path / f"{source_table}.csv"
                if not csv_path.exists():
                    print(f"skip {source_table}: {csv_path} does not exist")
                    continue

                df = pd.read_csv(csv_path)
                ods_table = f"ods_{source_table}"
                _replace_ods_table(cursor, ods_table, df)
                counts[ods_table] = len(df)
                print(f"loaded {ods_table}: {len(df)} rows")

            _rebuild_serving_layers(cursor)

    return counts


def _replace_ods_table(cursor, table_name: str, df: pd.DataFrame) -> None:
    quoted_table = _quote_identifier(table_name)
    column_defs = ", ".join(
        f"{_quote_identifier(column)} {_doris_type(df[column])}" for column in df.columns
    )
    quoted_columns = ", ".join(_quote_identifier(column) for column in df.columns)
    placeholders = ", ".join(["%s"] * len(df.columns))

    cursor.execute(f"DROP TABLE IF EXISTS {quoted_table}")
    cursor.execute(
        f"""
        CREATE TABLE {quoted_table} (
            {column_defs}
        )
        DUPLICATE KEY({_quote_identifier(df.columns[0])})
        DISTRIBUTED BY HASH({_quote_identifier(df.columns[0])}) BUCKETS 1
        PROPERTIES (
            "replication_num" = "1"
        )
        """
    )

    if df.empty:
        return

    rows = [
        tuple(None if pd.isna(value) else value for value in row)
        for row in df.itertuples(index=False, name=None)
    ]
    batch_size = 1000
    insert_sql = f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"
    for i in range(0, len(rows), batch_size):
        cursor.executemany(insert_sql, rows[i : i + batch_size])


def _rebuild_serving_layers(cursor) -> None:
    for statement in _layer_sql_statements():
        cursor.execute(statement)


def _layer_sql_statements() -> list[str]:
    return [
        """
        DROP TABLE IF EXISTS dwd_vehicle_prod_sales_monthly
        """,
        """
        CREATE TABLE dwd_vehicle_prod_sales_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            manufacturer_name,
            model_name,
            stat_type,
            CAST(data_month AS DATE) AS data_month,
            CAST(current_units AS DOUBLE) AS current_units,
            CAST(current_yoy_rate AS DOUBLE) AS yoy_rate
        FROM ods_fact_vehicle_prod_sales_monthly
        """,
        """
        DROP TABLE IF EXISTS dwd_nev_manufacturer_monthly
        """,
        """
        CREATE TABLE dwd_nev_manufacturer_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            manufacturer_name,
            vehicle_category,
            vehicle_segment,
            fuel_type,
            CAST(data_month AS DATE) AS data_month,
            CAST(production_current_units AS DOUBLE) AS production_current_units,
            CAST(sales_current_units AS DOUBLE) AS sales_current_units
        FROM ods_fact_nev_manufacturer_monthly
        """,
        """
        DROP TABLE IF EXISTS dwd_nev_overall_monthly
        """,
        """
        CREATE TABLE dwd_nev_overall_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            vehicle_category,
            vehicle_segment,
            fuel_type,
            CAST(data_month AS DATE) AS data_month,
            CAST(production_current_units AS DOUBLE) AS production_current_units,
            CAST(sales_current_units AS DOUBLE) AS sales_current_units
        FROM ods_fact_nev_overall_monthly
        """,
        """
        DROP TABLE IF EXISTS dwd_charging_infrastructure_monthly
        """,
        """
        CREATE TABLE dwd_charging_infrastructure_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            province,
            CAST(data_month AS DATE) AS data_month,
            metric_name,
            CAST(metric_value AS DOUBLE) AS metric_value,
            unit
        FROM ods_fact_charging_infrastructure_monthly
        """,
        """
        DROP TABLE IF EXISTS dwd_battery_installation_monthly
        """,
        """
        CREATE TABLE dwd_battery_installation_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            dimension_type,
            dimension_value,
            CAST(data_month AS DATE) AS data_month,
            metric_name,
            CAST(metric_value AS DOUBLE) AS metric_value,
            unit
        FROM ods_fact_battery_installation_monthly
        """,
        """
        DROP TABLE IF EXISTS dws_vehicle_sales_monthly
        """,
        """
        CREATE TABLE dws_vehicle_sales_monthly
        DISTRIBUTED BY HASH(manufacturer_name) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            manufacturer_name,
            model_name,
            SUM(CASE WHEN stat_type = '销量' THEN current_units ELSE 0 END) AS sales_units,
            SUM(CASE WHEN stat_type = '产量' THEN current_units ELSE 0 END) AS production_units
        FROM dwd_vehicle_prod_sales_monthly
        GROUP BY data_month, manufacturer_name, model_name
        """,
        """
        DROP TABLE IF EXISTS dws_nev_manufacturer_sales_monthly
        """,
        """
        CREATE TABLE dws_nev_manufacturer_sales_monthly
        DISTRIBUTED BY HASH(manufacturer_name) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            manufacturer_name,
            SUM(production_current_units) AS production_units,
            SUM(sales_current_units) AS sales_units
        FROM dwd_nev_manufacturer_monthly
        WHERE vehicle_category = '总计'
          AND vehicle_segment = '总计'
          AND fuel_type = '总计'
        GROUP BY data_month, manufacturer_name
        """,
        """
        DROP TABLE IF EXISTS dws_nev_market_monthly
        """,
        """
        CREATE TABLE dws_nev_market_monthly
        DISTRIBUTED BY HASH(data_month) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            SUM(production_current_units) AS production_units,
            SUM(sales_current_units) AS sales_units
        FROM dwd_nev_overall_monthly
        WHERE vehicle_category = '总计'
          AND vehicle_segment = '总计'
          AND fuel_type = '总计'
        GROUP BY data_month
        """,
        """
        DROP TABLE IF EXISTS dws_charging_province_monthly
        """,
        """
        CREATE TABLE dws_charging_province_monthly
        DISTRIBUTED BY HASH(province) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            province,
            metric_name,
            SUM(metric_value) AS metric_value,
            MAX(unit) AS unit
        FROM dwd_charging_infrastructure_monthly
        GROUP BY data_month, province, metric_name
        """,
        """
        DROP TABLE IF EXISTS dws_battery_structure_monthly
        """,
        """
        CREATE TABLE dws_battery_structure_monthly
        DISTRIBUTED BY HASH(dimension_value) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            dimension_type,
            dimension_value,
            metric_name,
            SUM(metric_value) AS metric_value,
            MAX(unit) AS unit
        FROM dwd_battery_installation_monthly
        GROUP BY data_month, dimension_type, dimension_value, metric_name
        """,
        """
        DROP TABLE IF EXISTS ads_nev_manufacturer_sales_rank
        """,
        """
        CREATE TABLE ads_nev_manufacturer_sales_rank
        DISTRIBUTED BY HASH(stat_year) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            YEAR(data_month) AS stat_year,
            manufacturer_name,
            SUM(sales_units) AS total_sales_units,
            RANK() OVER (
                PARTITION BY YEAR(data_month)
                ORDER BY SUM(sales_units) DESC
            ) AS sales_rank
        FROM dws_nev_manufacturer_sales_monthly
        GROUP BY YEAR(data_month), manufacturer_name
        """,
        """
        DROP TABLE IF EXISTS ads_nev_penetration_trend
        """,
        """
        CREATE TABLE ads_nev_penetration_trend
        DISTRIBUTED BY HASH(data_month) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            sales_units AS nev_sales_units,
            sales_units AS total_vehicle_sales_units,
            sales_units / NULLIF(sales_units, 0) AS penetration_rate
        FROM dws_nev_market_monthly
        """,
        """
        DROP TABLE IF EXISTS ads_vehicle_model_sales_rank
        """,
        """
        CREATE TABLE ads_vehicle_model_sales_rank
        DISTRIBUTED BY HASH(stat_year) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            YEAR(data_month) AS stat_year,
            manufacturer_name,
            model_name,
            SUM(sales_units) AS total_sales_units,
            RANK() OVER (
                PARTITION BY YEAR(data_month)
                ORDER BY SUM(sales_units) DESC
            ) AS sales_rank
        FROM dws_vehicle_sales_monthly
        GROUP BY YEAR(data_month), manufacturer_name, model_name
        """,
        """
        DROP TABLE IF EXISTS ads_charging_facility_province_distribution
        """,
        """
        CREATE TABLE ads_charging_facility_province_distribution
        DISTRIBUTED BY HASH(province) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            province,
            metric_name,
            metric_value,
            unit
        FROM dws_charging_province_monthly
        """,
        """
        DROP TABLE IF EXISTS ads_battery_material_share
        """,
        """
        CREATE TABLE ads_battery_material_share
        DISTRIBUTED BY HASH(material_type) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            dimension_value AS material_type,
            metric_name,
            metric_value,
            metric_value / NULLIF(SUM(metric_value) OVER (PARTITION BY data_month, metric_name), 0) AS share,
            unit
        FROM dws_battery_structure_monthly
        WHERE dimension_type = 'material_type'
        """,
        """
        DROP TABLE IF EXISTS ads_battery_vehicle_type_share
        """,
        """
        CREATE TABLE ads_battery_vehicle_type_share
        DISTRIBUTED BY HASH(vehicle_type) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            data_month,
            dimension_value AS vehicle_type,
            metric_name,
            metric_value,
            metric_value / NULLIF(SUM(metric_value) OVER (PARTITION BY data_month, metric_name), 0) AS share,
            unit
        FROM dws_battery_structure_monthly
        WHERE dimension_type = 'vehicle_type'
        """,
        """
        DROP TABLE IF EXISTS dwd_global_ev_sales_yearly
        """,
        """
        CREATE TABLE dwd_global_ev_sales_yearly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            country,
            ev_type,
            CAST(data_year AS BIGINT) AS data_year,
            CAST(sales_volume AS DOUBLE) AS sales_volume,
            unit
        FROM ods_fact_global_ev_sales_yearly
        """,
        """
        DROP TABLE IF EXISTS dwd_global_ev_stock_yearly
        """,
        """
        CREATE TABLE dwd_global_ev_stock_yearly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            country,
            ev_type,
            CAST(data_year AS BIGINT) AS data_year,
            CAST(stock_volume AS DOUBLE) AS stock_volume,
            unit
        FROM ods_fact_global_ev_stock_yearly
        """,
        """
        DROP TABLE IF EXISTS dwd_battery_production_monthly
        """,
        """
        CREATE TABLE dwd_battery_production_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            material_type,
            CAST(data_month AS DATE) AS data_month,
            metric_name,
            CAST(metric_value AS DOUBLE) AS metric_value,
            unit
        FROM ods_fact_battery_production_monthly
        """,
        """
        DROP TABLE IF EXISTS dwd_vehicle_production_province_monthly
        """,
        """
        CREATE TABLE dwd_vehicle_production_province_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            province,
            CAST(data_month AS DATE) AS data_month,
            metric_name,
            CAST(metric_value AS DOUBLE) AS metric_value,
            unit
        FROM ods_fact_vehicle_production_province_monthly
        """,
        """
        DROP TABLE IF EXISTS dwd_charging_operator_monthly
        """,
        """
        CREATE TABLE dwd_charging_operator_monthly
        DISTRIBUTED BY HASH(record_id) BUCKETS 4
        PROPERTIES ("replication_num" = "1")
        AS
        SELECT
            record_id,
            source_id,
            operator_name,
            CAST(data_month AS DATE) AS data_month,
            CAST(charging_volume AS DOUBLE) AS charging_volume,
            unit
        FROM ods_fact_charging_operator_monthly
        """,
    ]

def _doris_type(series: pd.Series) -> str:
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE"
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    return "VARCHAR(65533)"


def _quote_identifier(identifier: str) -> str:
    escaped = identifier.replace("`", "``")
    return f"`{escaped}`"


def _connect(**kwargs):
    import pymysql

    return pymysql.connect(**kwargs)


if __name__ == "__main__":
    print(f"Loading cleaned CSV files from {CLEANED_DIR} into Doris...\n")
    table_counts = build_warehouse()
    print(f"\nLoaded {len(table_counts)} ODS tables, {sum(table_counts.values())} rows")
