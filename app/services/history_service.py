from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from app.services.sql_executor import DorisConfig


class HistoryService:
    """
    查询历史记录服务，负责把问数链路的成功与失败记录写入 Doris 应用日志表。
    """

    def __init__(self, config: DorisConfig | None = None):
        self.config = config or DorisConfig.from_env()
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS query_history (
                        id                BIGINT,
                        created_at        DATETIME,
                        question          STRING,
                        sql_text          STRING,
                        success           BOOLEAN,
                        error_message     STRING,
                        row_count         INT,
                        chart_type        STRING,
                        execution_time_ms DOUBLE,
                        analysis          STRING,
                        session_id        VARCHAR(64)
                    )
                    ENGINE=OLAP
                    DUPLICATE KEY(id)
                    DISTRIBUTED BY HASH(id) BUCKETS 1
                    PROPERTIES (
                        "replication_num" = "1"
                    )
                    """
                )

                # 创建会话表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        session_id        VARCHAR(64),
                        title             STRING,
                        created_at        DATETIME,
                        updated_at        DATETIME
                    )
                    ENGINE=OLAP
                    UNIQUE KEY(session_id)
                    DISTRIBUTED BY HASH(session_id) BUCKETS 1
                    PROPERTIES (
                        "replication_num" = "1"
                    )
                    """
                )

                # 创建消息记录表
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        message_id        VARCHAR(64),
                        session_id        VARCHAR(64),
                        msg_role          VARCHAR(16),
                        content           STRING,
                        created_at        DATETIME
                    )
                    ENGINE=OLAP
                    DUPLICATE KEY(message_id)
                    DISTRIBUTED BY HASH(session_id) BUCKETS 1
                    PROPERTIES (
                        "replication_num" = "1"
                    )
                    """
                )

    def record_success(
        self,
        *,
        question: str,
        sql: Optional[str],
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
            with conn.cursor() as cursor:
                record_id = self._next_id(cursor)
                cursor.execute(
                    """
                    INSERT INTO query_history (
                        id,
                        created_at,
                        question,
                        sql_text,
                        success,
                        error_message,
                        row_count,
                        chart_type,
                        execution_time_ms,
                        analysis
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record_id,
                        datetime.now(),
                        question,
                        sql,
                        success,
                        error_message,
                        row_count,
                        chart_type,
                        execution_time_ms,
                        analysis,
                    ),
                )

        return record_id

    def create_or_update_session(self, session_id: str, title: str) -> None:
        now = datetime.now()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT created_at, title FROM chat_sessions WHERE session_id = %s", (session_id,))
                row = cursor.fetchone()
                if row:
                    # Session exists, update updated_at but keep original title and created_at
                    # For Doris UNIQUE KEY, we re-insert the row with the old values
                    created_at, orig_title = row
                    cursor.execute(
                        """
                        INSERT INTO chat_sessions (session_id, title, created_at, updated_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, orig_title, created_at, now)
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO chat_sessions (session_id, title, created_at, updated_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, title, now, now)
                    )

    def update_session_title(self, session_id: str, new_title: str) -> None:
        now = datetime.now()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT created_at FROM chat_sessions WHERE session_id = %s", (session_id,))
                row = cursor.fetchone()
                if row:
                    created_at = row[0]
                    cursor.execute(
                        """
                        INSERT INTO chat_sessions (session_id, title, created_at, updated_at)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, new_title, created_at, now)
                    )

    def add_chat_messages(self, session_id: str, messages: list[dict]) -> None:
        import uuid
        now = datetime.now()
        with self._connect() as conn:
            with conn.cursor() as cursor:
                for msg in messages:
                    msg_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO chat_messages (message_id, session_id, msg_role, content, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (msg_id, session_id, msg.get("role"), msg.get("content"), now)
                    )

    def get_sessions(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT session_id, title, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC LIMIT %s",
                    (limit,)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "session_id": row[0],
                        "title": row[1],
                        "created_at": row[2].isoformat() if row[2] else None,
                        "updated_at": row[3].isoformat() if row[3] else None
                    }
                    for row in rows
                ]

    def get_messages(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT msg_role, content, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC, CASE WHEN msg_role = 'user' THEN 1 ELSE 2 END ASC",
                    (session_id,)
                )
                rows = cursor.fetchall()
                return [
                    {
                        "role": row[0],
                        "content": row[1],
                        "created_at": row[2].isoformat() if row[2] else None
                    }
                    for row in rows
                ]

    def delete_session(self, session_id: str) -> None:
        """删除指定会话及其所有消息记录"""
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM chat_messages WHERE session_id = %s",
                    (session_id,)
                )
                cursor.execute(
                    "DELETE FROM chat_sessions WHERE session_id = %s",
                    (session_id,)
                )

    def _next_id(self, cursor) -> int:
        cursor.execute("SELECT COALESCE(MAX(id), 0) FROM query_history")
        row = cursor.fetchone()
        return int(row[0]) + 1

    @contextmanager
    def _connect(self) -> Iterator[object]:
        conn = _pymysql_connect(
            host=self.config.host,
            port=self.config.query_port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset="utf8mb4",
        )
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _pymysql_connect(**kwargs):
    import pymysql

    return pymysql.connect(**kwargs)
