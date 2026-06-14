import pytest

from app.services.sql_guard import SQLGuard, SQLGuardError, guard_sql


def test_select_without_limit_gets_default_limit():
    guard = SQLGuard(default_limit=25)

    sql = guard.validate_and_rewrite(
        "SELECT manufacturer_name, total_sales_units "
        "FROM ads_nev_manufacturer_sales_rank "
        "ORDER BY total_sales_units DESC"
    )

    assert sql.endswith("LIMIT 25")
    assert "ads_nev_manufacturer_sales_rank" in sql


def test_select_with_existing_limit_is_preserved():
    guard = SQLGuard(default_limit=100)

    sql = guard.validate_and_rewrite(
        "SELECT manufacturer_name, total_sales_units FROM ads_nev_manufacturer_sales_rank LIMIT 5"
    )

    assert sql == "SELECT manufacturer_name, total_sales_units FROM ads_nev_manufacturer_sales_rank LIMIT 5"


def test_with_query_can_reference_cte_alias_and_allowed_base_table():
    guard = SQLGuard(default_limit=10)

    sql = guard.validate_and_rewrite(
        """
        WITH ranked AS (
            SELECT manufacturer_name, SUM(sales_current_units) AS total_sales
            FROM dws_nev_manufacturer_sales_monthly
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


def test_data_month_between_date_bounds_casts_column_for_postgres():
    guard = SQLGuard(default_limit=100)

    sql = guard.validate_and_rewrite(
        """
        SELECT manufacturer_name, SUM(sales_current_units) AS volume
        FROM dws_nev_manufacturer_sales_monthly
        WHERE data_month BETWEEN CAST('2022-01-01' AS DATE)
          AND CAST('2022-12-31' AS DATE)
        GROUP BY manufacturer_name
        ORDER BY volume DESC
        """
    )

    assert "CAST(data_month AS DATE) BETWEEN" in sql
    assert "CAST('2022-01-01' AS DATE)" in sql
    assert "CAST('2022-12-31' AS DATE)" in sql


def test_data_month_date_comparison_casts_column_for_postgres():
    guard = SQLGuard(default_limit=100)

    sql = guard.validate_and_rewrite(
        """
        SELECT province, SUM(metric_value) AS charging_facility_count
        FROM dws_charging_province_monthly
        WHERE data_month = DATE '2022-12-31'
        GROUP BY province
        """
    )

    assert "CAST(data_month AS DATE) = CAST('2022-12-31' AS DATE)" in sql


@pytest.mark.parametrize(
    "dangerous_sql",
    [
        "DELETE FROM ads_nev_manufacturer_sales_rank WHERE manufacturer_name = 'test'",
        "DROP TABLE ads_nev_manufacturer_sales_rank",
        "INSERT INTO ads_nev_manufacturer_sales_rank VALUES (99, 'x')",
        "UPDATE ads_nev_manufacturer_sales_rank SET manufacturer_name = 'x'",
        "CREATE TABLE tmp AS SELECT * FROM ads_nev_manufacturer_sales_rank",
        "TRUNCATE TABLE ads_nev_manufacturer_sales_rank",
        "SELECT * INTO OUTFILE '/tmp/leak.csv' FROM ads_nev_manufacturer_sales_rank",
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
            "SELECT manufacturer_name FROM ads_nev_manufacturer_sales_rank; DROP TABLE ads_nev_manufacturer_sales_rank;"
        )


def test_rejects_tables_outside_whitelist():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="not allowed"):
        guard.validate_and_rewrite("SELECT id FROM user_credentials")


def test_rejects_qualified_table_names_to_avoid_bypassing_whitelist():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="Unqualified"):
        guard.validate_and_rewrite("SELECT manufacturer_name FROM main.ads_nev_manufacturer_sales_rank")


def test_rejects_invalid_sql():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="Invalid SQL"):
        guard.validate_and_rewrite("SELECC FROM")


def test_guard_sql_function_uses_default_guard():
    sql = guard_sql("SELECT manufacturer_name FROM ads_nev_manufacturer_sales_rank")

    assert sql == "SELECT manufacturer_name FROM ads_nev_manufacturer_sales_rank LIMIT 100"


def test_rejects_old_ods_or_fact_tables_by_default():
    guard = SQLGuard()

    with pytest.raises(SQLGuardError, match="not allowed"):
        guard.validate_and_rewrite("SELECT manufacturer_name FROM fact_nev_manufacturer_monthly")
