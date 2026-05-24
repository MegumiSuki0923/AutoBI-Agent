import pytest

from app.services.sql_guard import SQLGuard, SQLGuardError, guard_sql


def test_select_without_limit_gets_default_limit():
    guard = SQLGuard(default_limit=25)

    sql = guard.validate_and_rewrite(
        "SELECT manufacturer_name, sales_current_units "
        "FROM fact_nev_manufacturer_monthly "
        "ORDER BY sales_current_units DESC"
    )

    assert sql.endswith("LIMIT 25")
    assert "fact_nev_manufacturer_monthly" in sql


def test_select_with_existing_limit_is_preserved():
    guard = SQLGuard(default_limit=100)

    sql = guard.validate_and_rewrite(
        "SELECT source_id, file_name FROM dim_data_source LIMIT 5"
    )

    assert sql == "SELECT source_id, file_name FROM dim_data_source LIMIT 5"


def test_with_query_can_reference_cte_alias_and_allowed_base_table():
    guard = SQLGuard(default_limit=10)

    sql = guard.validate_and_rewrite(
        """
        WITH ranked AS (
            SELECT manufacturer_name, SUM(sales_current_units) AS total_sales
            FROM fact_nev_manufacturer_monthly
            GROUP BY manufacturer_name
        )
        SELECT manufacturer_name, total_sales
        FROM ranked
        ORDER BY total_sales DESC
        """
    )

    assert sql.startswith("WITH ranked AS")
    assert "FROM ranked" in sql
    assert sql.endswith("LIMIT 10")


def test_data_month_between_date_bounds_casts_column_for_duckdb():
    guard = SQLGuard(default_limit=100)

    sql = guard.validate_and_rewrite(
        """
        SELECT manufacturer_name, SUM(sales_current_units) AS volume
        FROM fact_nev_manufacturer_monthly
        WHERE data_month BETWEEN CAST('2022-01-01' AS DATE)
          AND CAST('2022-12-31' AS DATE)
        GROUP BY manufacturer_name
        ORDER BY volume DESC
        """
    )

    assert "CAST(data_month AS DATE) BETWEEN" in sql
    assert "CAST('2022-01-01' AS DATE)" in sql
    assert "CAST('2022-12-31' AS DATE)" in sql


def test_data_month_date_comparison_casts_column_for_duckdb():
    guard = SQLGuard(default_limit=100)

    sql = guard.validate_and_rewrite(
        """
        SELECT province, SUM(metric_value) AS charging_facility_count
        FROM fact_charging_infrastructure_monthly
        WHERE data_month = DATE '2022-12-31'
        GROUP BY province
        """
    )

    assert "CAST(data_month AS DATE) = CAST('2022-12-31' AS DATE)" in sql


@pytest.mark.parametrize(
    "dangerous_sql",
    [
        "DELETE FROM fact_nev_manufacturer_monthly WHERE manufacturer_name = 'test'",
        "DROP TABLE fact_nev_manufacturer_monthly",
        "INSERT INTO dim_data_source VALUES (99, 'x', 'x')",
        "UPDATE dim_data_source SET file_name = 'x'",
        "CREATE TABLE tmp AS SELECT * FROM dim_data_source",
        "TRUNCATE TABLE dim_data_source",
        "COPY dim_data_source TO '/tmp/leak.csv'",
    ],
)
def test_rejects_non_select_sql(dangerous_sql):
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="SELECT"):
        guard.validate_and_rewrite(dangerous_sql)


def test_rejects_multiple_statements_even_if_first_is_select():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="single SQL statement"):
        guard.validate_and_rewrite(
            "SELECT source_id FROM dim_data_source; DROP TABLE dim_data_source;"
        )


def test_rejects_tables_outside_whitelist():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="not allowed"):
        guard.validate_and_rewrite("SELECT id FROM user_credentials")


def test_rejects_qualified_table_names_to_avoid_bypassing_whitelist():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="Unqualified"):
        guard.validate_and_rewrite("SELECT source_id FROM main.dim_data_source")


def test_rejects_invalid_sql():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="Invalid SQL"):
        guard.validate_and_rewrite("SELECC FROM")


def test_guard_sql_function_uses_default_guard():
    sql = guard_sql("SELECT source_id FROM dim_data_source")

    assert sql == "SELECT source_id FROM dim_data_source LIMIT 100"
