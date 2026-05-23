"""测试数据清洗和 DuckDB 入库流程"""

from pathlib import Path

import duckdb

from scripts.build_duckdb import build_database
from scripts.clean_raw_data import clean_all


def test_clean_and_build(tmp_path):
    """测试完整的清洗 + 入库流程"""
    # Step 1: 清洗原始数据到临时目录
    import scripts.clean_raw_data as cleaner

    original_dir = cleaner.CLEANED_DIR
    cleaner.CLEANED_DIR = tmp_path / "cleaned"
    try:
        counts = clean_all()
    finally:
        cleaner.CLEANED_DIR = original_dir

    # 确认 6 个 CSV 都生成了
    assert len(counts) == 6
    for name, row_count in counts.items():
        csv_path = tmp_path / "cleaned" / f"{name}.csv"
        assert csv_path.exists(), f"{name}.csv 不存在"
        assert row_count > 0, f"{name} 行数为 0"

    # Step 2: 从临时 CSV 入库
    import scripts.build_duckdb as builder

    original_cleaned = builder.CLEANED_DIR
    builder.CLEANED_DIR = tmp_path / "cleaned"
    db_path = tmp_path / "autobi.duckdb"
    try:
        db_counts = build_database(db_path)
    finally:
        builder.CLEANED_DIR = original_cleaned

    # 验证入库行数与清洗行数一致
    for name in counts:
        assert db_counts[name] == counts[name], (
            f"{name}: 清洗 {counts[name]} 行 vs 入库 {db_counts[name]} 行"
        )


def test_expected_tables_exist(tmp_path):
    """验证 DuckDB 中至少包含 6 张预期的表"""
    import scripts.build_duckdb as builder
    import scripts.clean_raw_data as cleaner

    # 清洗
    original_dir = cleaner.CLEANED_DIR
    cleaner.CLEANED_DIR = tmp_path / "cleaned"
    try:
        clean_all()
    finally:
        cleaner.CLEANED_DIR = original_dir

    # 入库
    original_cleaned = builder.CLEANED_DIR
    builder.CLEANED_DIR = tmp_path / "cleaned"
    db_path = tmp_path / "autobi.duckdb"
    try:
        build_database(db_path)
    finally:
        builder.CLEANED_DIR = original_cleaned

    with duckdb.connect(str(db_path), read_only=True) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}

    expected = {
        "dim_data_source",
        "fact_vehicle_prod_sales_monthly",
        "fact_nev_manufacturer_monthly",
        "fact_nev_overall_monthly",
        "fact_charging_infrastructure_monthly",
        "fact_battery_installation_monthly",
    }
    assert expected.issubset(tables), f"缺少表: {expected - tables}"


def test_nev_manufacturer_no_duplicates(tmp_path):
    """验证 NEV 厂商表按业务键去重后无重复"""
    import scripts.build_duckdb as builder
    import scripts.clean_raw_data as cleaner

    original_dir = cleaner.CLEANED_DIR
    cleaner.CLEANED_DIR = tmp_path / "cleaned"
    try:
        clean_all()
    finally:
        cleaner.CLEANED_DIR = original_dir

    original_cleaned = builder.CLEANED_DIR
    builder.CLEANED_DIR = tmp_path / "cleaned"
    db_path = tmp_path / "autobi.duckdb"
    try:
        build_database(db_path)
    finally:
        builder.CLEANED_DIR = original_cleaned

    with duckdb.connect(str(db_path), read_only=True) as conn:
        dup_count = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT manufacturer_name, vehicle_category, vehicle_segment,
                       fuel_type, data_month, COUNT(*) as cnt
                FROM fact_nev_manufacturer_monthly
                GROUP BY manufacturer_name, vehicle_category, vehicle_segment,
                         fuel_type, data_month
                HAVING cnt > 1
            )
        """).fetchone()[0]

    assert dup_count == 0, f"仍有 {dup_count} 组重复"


def test_charging_province_clean(tmp_path):
    """验证充电设施表 province 不包含非省份值"""
    import scripts.build_duckdb as builder
    import scripts.clean_raw_data as cleaner

    original_dir = cleaner.CLEANED_DIR
    cleaner.CLEANED_DIR = tmp_path / "cleaned"
    try:
        clean_all()
    finally:
        cleaner.CLEANED_DIR = original_dir

    original_cleaned = builder.CLEANED_DIR
    builder.CLEANED_DIR = tmp_path / "cleaned"
    db_path = tmp_path / "autobi.duckdb"
    try:
        build_database(db_path)
    finally:
        builder.CLEANED_DIR = original_cleaned

    dirty_values = {"交流桩", "直流桩", "同比", "环比"}

    with duckdb.connect(str(db_path), read_only=True) as conn:
        provinces = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT province FROM fact_charging_infrastructure_monthly"
            ).fetchall()
        }

    overlap = provinces & dirty_values
    assert not overlap, f"province 仍包含脏数据: {overlap}"


def test_standard_questions_queryable(tmp_path):
    """验证 3 个标准业务问题可查询出非空结果"""
    import scripts.build_duckdb as builder
    import scripts.clean_raw_data as cleaner

    original_dir = cleaner.CLEANED_DIR
    cleaner.CLEANED_DIR = tmp_path / "cleaned"
    try:
        clean_all()
    finally:
        cleaner.CLEANED_DIR = original_dir

    original_cleaned = builder.CLEANED_DIR
    builder.CLEANED_DIR = tmp_path / "cleaned"
    db_path = tmp_path / "autobi.duckdb"
    try:
        build_database(db_path)
    finally:
        builder.CLEANED_DIR = original_cleaned

    with duckdb.connect(str(db_path), read_only=True) as conn:
        # 注意：CSV 导入后 data_month 为 VARCHAR，需要 CAST 为 DATE
        # 问题1: 厂商新能源销量排名
        top_manufacturers = conn.execute("""
            SELECT manufacturer_name, SUM(sales_current_units) AS vol
            FROM fact_nev_manufacturer_monthly
            WHERE CAST(data_month AS DATE) BETWEEN DATE '2022-01-01' AND DATE '2022-12-31'
              AND vehicle_category = '总计'
            GROUP BY manufacturer_name
            ORDER BY vol DESC LIMIT 5
        """).fetchall()

        # 问题2: 车型销量排名
        top_models = conn.execute("""
            SELECT model_name, SUM(current_units) AS vol
            FROM fact_vehicle_prod_sales_monthly
            WHERE stat_type = '销量'
              AND CAST(data_month AS DATE) BETWEEN DATE '2022-01-01' AND DATE '2022-12-31'
            GROUP BY model_name
            ORDER BY vol DESC LIMIT 5
        """).fetchall()

        # 问题3: 新能源渗透率
        penetration = conn.execute("""
            WITH total_vehicle AS (
                SELECT data_month, SUM(current_units) AS total_sales
                FROM fact_vehicle_prod_sales_monthly
                WHERE stat_type = '销量'
                GROUP BY data_month
            ),
            nev AS (
                SELECT data_month, SUM(sales_current_units) AS nev_sales
                FROM fact_nev_overall_monthly
                WHERE vehicle_category = '总计'
                  AND vehicle_segment = '总计'
                  AND fuel_type = '总计'
                GROUP BY data_month
            )
            SELECT nev.data_month,
                   nev.nev_sales / NULLIF(total_vehicle.total_sales, 0)
            FROM nev
            JOIN total_vehicle ON nev.data_month = total_vehicle.data_month
            ORDER BY nev.data_month LIMIT 5
        """).fetchall()

    assert top_manufacturers, "厂商销量排名查询结果为空"
    assert top_models, "车型销量排名查询结果为空"
    assert penetration, "渗透率查询结果为空"
