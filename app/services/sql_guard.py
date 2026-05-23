from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError


DEFAULT_ALLOWED_TABLES = frozenset(
    {
        "dim_data_source",
        "fact_vehicle_prod_sales_monthly",
        "fact_nev_manufacturer_monthly",
        "fact_nev_overall_monthly",
        "fact_charging_infrastructure_monthly",
        "fact_battery_installation_monthly",
    }
)


class SQLGuardError(ValueError):
    """SQL 安全校验失败。"""


@dataclass(frozen=True)
class SQLGuard:
    """
    使用 sqlglot 对 Text-to-SQL 结果做执行前安全校验。

    校验边界：
    - 只允许单条顶层 SELECT 查询，WITH 查询会被解析为 SELECT。
    - 只允许访问白名单内的物理表。
    - 外层查询缺少 LIMIT 时自动补充默认 LIMIT。
    """

    allowed_tables: Iterable[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TABLES)
    default_limit: int = 100
    dialect: str = "duckdb"

    def __post_init__(self) -> None:
        if self.default_limit <= 0:
            raise ValueError("default_limit must be greater than 0")

        normalized = frozenset(_normalize_name(table) for table in self.allowed_tables)
        object.__setattr__(self, "allowed_tables", normalized)

    def validate_and_rewrite(self, sql: str) -> str:
        """
        校验 SQL 并返回可执行 SQL。

        如果外层 SELECT 没有 LIMIT，会补充 `LIMIT {default_limit}`。
        """
        expression = self._parse_single_statement(sql)
        self._validate_select_only(expression)
        self._validate_tables(expression)
        return self._with_limit(expression)

    def _parse_single_statement(self, sql: str) -> exp.Expression:
        if not sql or not sql.strip():
            raise SQLGuardError("Invalid SQL: query is empty")

        try:
            expressions = [
                expression
                for expression in sqlglot.parse(sql, read=self.dialect)
                if expression is not None
            ]
        except ParseError as exc:
            raise SQLGuardError(f"Invalid SQL: {exc}") from exc

        if not expressions:
            raise SQLGuardError("Invalid SQL: query is empty")

        if len(expressions) != 1:
            raise SQLGuardError("Only a single SQL statement is allowed")

        return expressions[0]

    def _validate_select_only(self, expression: exp.Expression) -> None:
        if not isinstance(expression, exp.Select):
            raise SQLGuardError("Only SELECT statements are allowed")

    def _validate_tables(self, expression: exp.Expression) -> None:
        cte_aliases = {
            _normalize_name(cte.alias)
            for cte in expression.find_all(exp.CTE)
            if cte.alias
        }

        for table in expression.find_all(exp.Table):
            table_name = _normalize_name(table.name)

            if table_name in cte_aliases:
                continue

            if table.catalog or table.db:
                raise SQLGuardError(
                    "Unqualified table names are required for whitelist validation"
                )

            if table_name not in self.allowed_tables:
                allowed = ", ".join(sorted(self.allowed_tables))
                raise SQLGuardError(
                    f"Table '{table.name}' is not allowed. Allowed tables: {allowed}"
                )

    def _with_limit(self, expression: exp.Expression) -> str:
        if expression.args.get("limit") is None:
            expression = expression.limit(self.default_limit)

        return expression.sql(dialect=self.dialect)


def guard_sql(sql: str, default_limit: int = 100) -> str:
    """使用默认表白名单校验并改写 SQL。"""
    return SQLGuard(default_limit=default_limit).validate_and_rewrite(sql)


def _normalize_name(name: str) -> str:
    return name.strip().lower()
