import duckdb

from app.services.history_service import HistoryService


def test_history_service_creates_query_history_table(tmp_path):
    db_path = tmp_path / "history.duckdb"

    HistoryService(db_path=db_path)

    with duckdb.connect(str(db_path), read_only=True) as conn:
        table_names = {
            row[0]
            for row in conn.execute("SHOW TABLES").fetchall()
        }

    assert "query_history" in table_names


def test_record_success_saves_query_metadata(tmp_path):
    db_path = tmp_path / "history.duckdb"
    service = HistoryService(db_path=db_path)

    record_id = service.record_success(
        question="2022 年各厂商新能源汽车销量排名如何？",
        sql="SELECT brand, SUM(sales) AS total_sales FROM fact_nev_manufacturer_monthly GROUP BY brand LIMIT 5",
        row_count=5,
        chart_type="bar",
        execution_time_ms=123.45,
        analysis="比亚迪销量领先，特斯拉位列第二。",
    )

    with duckdb.connect(str(db_path), read_only=True) as conn:
        row = conn.execute(
            """
            SELECT
                id,
                created_at,
                question,
                sql,
                success,
                error_message,
                row_count,
                chart_type,
                execution_time_ms,
                analysis
            FROM query_history
            """
        ).fetchone()

    assert record_id == 1
    assert row[0] == 1
    assert row[1] is not None
    assert row[2] == "2022 年各厂商新能源汽车销量排名如何？"
    assert row[3].startswith("SELECT brand")
    assert row[4] is True
    assert row[5] is None
    assert row[6] == 5
    assert row[7] == "bar"
    assert row[8] == 123.45
    assert row[9] == "比亚迪销量领先，特斯拉位列第二。"


def test_record_failure_saves_error_reason(tmp_path):
    db_path = tmp_path / "history.duckdb"
    service = HistoryService(db_path=db_path)

    record_id = service.record_failure(
        question="删除所有数据",
        error_message="Only SELECT statements are allowed",
        sql="DELETE FROM fact_nev_manufacturer_monthly",
        execution_time_ms=8.9,
    )

    with duckdb.connect(str(db_path), read_only=True) as conn:
        row = conn.execute(
            """
            SELECT
                id,
                question,
                sql,
                success,
                error_message,
                row_count,
                chart_type,
                execution_time_ms,
                analysis
            FROM query_history
            """
        ).fetchone()

    assert record_id == 1
    assert row == (
        1,
        "删除所有数据",
        "DELETE FROM fact_nev_manufacturer_monthly",
        False,
        "Only SELECT statements are allowed",
        0,
        None,
        8.9,
        None,
    )


def test_history_ids_auto_increment(tmp_path):
    db_path = tmp_path / "history.duckdb"
    service = HistoryService(db_path=db_path)

    first_id = service.record_failure(
        question="错误问题 1",
        error_message="SQL generation failed",
    )
    second_id = service.record_failure(
        question="错误问题 2",
        error_message="SQL execution failed",
    )

    assert first_id == 1
    assert second_id == 2


def test_memory_database_keeps_schema_for_service_lifetime():
    service = HistoryService(db_path=":memory:")

    success_id = service.record_success(
        question="查询销量",
        sql="SELECT 1",
        row_count=1,
        chart_type="metric",
        execution_time_ms=1.2,
        analysis="返回 1 行。",
    )
    failure_id = service.record_failure(
        question="删除数据",
        error_message="Only SELECT statements are allowed",
    )

    assert success_id == 1
    assert failure_id == 2
