from __future__ import annotations

from app.services.history_service import HistoryService
from app.services.sql_executor import DorisConfig


class FakeCursor:
    def __init__(self):
        self.statements: list[str] = []
        self.params: list[tuple[object, ...] | None] = []
        self.max_id = 0
        self.inserted: list[tuple[object, ...]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.statements.append(str(sql))
        self.params.append(params)
        normalized = " ".join(str(sql).lower().split())
        if normalized.startswith("insert into query_history"):
            self.max_id = int(params[0])
            self.inserted.append(params)

    def fetchone(self):
        return (self.max_id,)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_history_service_creates_doris_query_history_table(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr("app.services.history_service._pymysql_connect", lambda **kwargs: connection)

    HistoryService(config=DorisConfig())

    ddl = "\n".join(cursor.statements).lower()
    assert "create table if not exists query_history" in ddl
    assert "engine=olap" in ddl
    assert connection.committed is True


def test_record_success_saves_query_metadata_to_doris(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr("app.services.history_service._pymysql_connect", lambda **kwargs: connection)
    service = HistoryService(config=DorisConfig())

    record_id = service.record_success(
        question="2022 年各厂商新能源汽车销量排名如何？",
        sql="SELECT manufacturer_name FROM ads_nev_manufacturer_sales_rank LIMIT 5",
        row_count=5,
        chart_type="bar",
        execution_time_ms=123.45,
        analysis="比亚迪销量领先，特斯拉位列第二。",
    )

    assert record_id == 1
    assert cursor.inserted[-1][0] == 1
    assert cursor.inserted[-1][3].startswith("SELECT manufacturer_name")
    assert cursor.inserted[-1][4] is True
    assert cursor.inserted[-1][7] == "bar"


def test_history_ids_auto_increment_in_application_for_doris(monkeypatch):
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr("app.services.history_service._pymysql_connect", lambda **kwargs: connection)
    service = HistoryService(config=DorisConfig())

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
