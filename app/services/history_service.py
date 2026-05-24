from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

import duckdb


class HistoryService:
    """
    查询历史记录服务，负责把问数链路的成功与失败记录写入 DuckDB。
    """

    DEFAULT_DB_PATH = "data/autobi.duckdb"

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = str(db_path)
        self._memory_connection: Optional[duckdb.DuckDBPyConnection] = None
        self._ensure_database_parent()
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("CREATE SEQUENCE IF NOT EXISTS query_history_id_seq START 1")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_history (
                    id                INTEGER PRIMARY KEY DEFAULT nextval('query_history_id_seq'),
                    created_at        TIMESTAMP,
                    question          VARCHAR,
                    sql               VARCHAR,
                    success           BOOLEAN,
                    error_message     VARCHAR,
                    row_count         INTEGER,
                    chart_type        VARCHAR,
                    execution_time_ms DOUBLE,
                    analysis          VARCHAR
                )
                """
            )

    def record_success(
        self,
        *,
        question: str,
        sql: str,
        row_count: int,
        chart_type: Optional[str],
        execution_time_ms: float,
        analysis: Optional[str] = None,
    ) -> int:
        return self._insert_record(
            question=question,
            sql=sql,
            success=True,
            error_message=None,
            row_count=row_count,
            chart_type=chart_type,
            execution_time_ms=execution_time_ms,
            analysis=analysis,
        )

    def record_failure(
        self,
        *,
        question: str,
        error_message: str,
        sql: Optional[str] = None,
        execution_time_ms: float = 0.0,
    ) -> int:
        return self._insert_record(
            question=question,
            sql=sql,
            success=False,
            error_message=error_message,
            row_count=0,
            chart_type=None,
            execution_time_ms=execution_time_ms,
            analysis=None,
        )

    def _insert_record(
        self,
        *,
        question: str,
        sql: Optional[str],
        success: bool,
        error_message: Optional[str],
        row_count: int,
        chart_type: Optional[str],
        execution_time_ms: float,
        analysis: Optional[str],
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO query_history (
                    created_at,
                    question,
                    sql,
                    success,
                    error_message,
                    row_count,
                    chart_type,
                    execution_time_ms,
                    analysis
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                [
                    datetime.now(),
                    question,
                    sql,
                    success,
                    error_message,
                    row_count,
                    chart_type,
                    execution_time_ms,
                    analysis,
                ],
            ).fetchone()

        return int(row[0])

    @contextmanager
    def _connect(self) -> Iterator[duckdb.DuckDBPyConnection]:
        if self.db_path == ":memory:":
            if self._memory_connection is None:
                self._memory_connection = duckdb.connect(self.db_path)
            yield self._memory_connection
            return

        conn = duckdb.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_database_parent(self) -> None:
        if self.db_path == ":memory:":
            return
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
