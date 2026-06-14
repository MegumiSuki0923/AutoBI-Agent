from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class DorisConfig:
    host: str = "127.0.0.1"
    query_port: int = 9030
    user: str = "root"
    password: str = ""
    database: str = "autobi"

    @classmethod
    def from_env(cls) -> "DorisConfig":
        return cls(
            host=os.getenv("DORIS_HOST", cls.host),
            query_port=int(os.getenv("DORIS_QUERY_PORT", str(cls.query_port))),
            user=os.getenv("DORIS_USER", cls.user),
            password=os.getenv("DORIS_PASSWORD", cls.password),
            database=os.getenv("DORIS_DATABASE", cls.database),
        )


class SQLExecutor:
    """
    Doris SQL 执行器，通过 Doris FE 的 MySQL 协议运行经 SQLGuard 校验后的只读查询。
    """

    def __init__(self, config: DorisConfig | None = None):
        self.config = config or DorisConfig.from_env()

    def execute(self, sql: str) -> tuple[list[str], list[list[Any]]]:
        """
        执行一条 SQL 查询语句。

        返回:
            一个元组 (columns, rows):
                - columns: 包含字段名（表头）的列表。
                - rows: 包含每一行数据的二维列表。
        """
        with _pymysql_connect(
            host=self.config.host,
            port=self.config.query_port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset="utf8mb4",
        ) as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql)
                columns = [desc[0] for desc in cursor.description or []]
                rows = [list(row) for row in cursor.fetchall()]

        return columns, rows


def _pymysql_connect(**kwargs):
    import pymysql

    return pymysql.connect(**kwargs)
