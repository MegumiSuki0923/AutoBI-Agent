import pytest

from app.services.sql_executor import DorisConfig, SQLExecutor
from app.services.sql_guard import SQLGuard


class FakeCursor:
    description = (("num",), ("brand",))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.sql = sql

    def fetchall(self):
        return ((1, "Tesla"), (2, "BYD"))


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self.cursor_obj


def test_doris_config_reads_doris_environment(monkeypatch):
    monkeypatch.setenv("DORIS_HOST", "doris-fe")
    monkeypatch.setenv("DORIS_QUERY_PORT", "9030")
    monkeypatch.setenv("DORIS_USER", "root")
    monkeypatch.setenv("DORIS_PASSWORD", "secret")
    monkeypatch.setenv("DORIS_DATABASE", "autobi_test")

    config = DorisConfig.from_env()

    assert config.host == "doris-fe"
    assert config.query_port == 9030
    assert config.user == "root"
    assert config.password == "secret"
    assert config.database == "autobi_test"


def test_sql_executor_uses_doris_mysql_protocol(monkeypatch):
    captured = {}
    connection = FakeConnection()

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setattr("app.services.sql_executor._pymysql_connect", fake_connect)

    executor = SQLExecutor(
        config=DorisConfig(
            host="127.0.0.1",
            query_port=9030,
            user="root",
            password="",
            database="autobi",
        )
    )
    columns, rows = executor.execute("SELECT 1 AS num, 'Tesla' AS brand")

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9030
    assert captured["database"] == "autobi"
    assert columns == ["num", "brand"]
    assert rows == [[1, "Tesla"], [2, "BYD"]]


def test_sql_executor_runs_guarded_ads_query(monkeypatch):
    monkeypatch.setattr("app.services.sql_executor._pymysql_connect", lambda **kwargs: FakeConnection())
    executor = SQLExecutor()

    sql = SQLGuard(default_limit=100).validate_and_rewrite(
        """
        SELECT manufacturer_name, total_sales_units
        FROM ads_nev_manufacturer_sales_rank
        WHERE stat_year = 2022
        ORDER BY sales_rank
        LIMIT 5
        """
    )

    columns, rows = executor.execute(sql)

    assert columns == ["num", "brand"]
    assert rows[0] == [1, "Tesla"]
