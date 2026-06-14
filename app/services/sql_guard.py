from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import sqlglot
from sqlglot import expressions as exp
from sqlglot.errors import ParseError


DEFAULT_ALLOWED_TABLES = frozenset(
    {
        "dwd_vehicle_prod_sales_monthly",
        "dwd_nev_manufacturer_monthly",
        "dwd_nev_overall_monthly",
        "dwd_charging_infrastructure_monthly",
        "dwd_battery_installation_monthly",
        "dws_vehicle_sales_monthly",
        "dws_nev_manufacturer_sales_monthly",
        "dws_nev_market_monthly",
        "dws_charging_province_monthly",
        "dws_battery_structure_monthly",
        "ads_nev_manufacturer_sales_rank",
        "ads_nev_penetration_trend",
        "ads_vehicle_model_sales_rank",
        "ads_charging_facility_province_distribution",
        "ads_battery_material_share",
        "ads_battery_vehicle_type_share",
        "dim_time", "ods_dim_time", "dwd_dim_time",
        "dim_manufacturer", "ods_dim_manufacturer", "dwd_dim_manufacturer",
        "dim_vehicle_model", "ods_dim_vehicle_model", "dwd_dim_vehicle_model",
        "dim_province", "ods_dim_province", "dwd_dim_province",
        "dim_fuel_type", "ods_dim_fuel_type", "dwd_dim_fuel_type",
        "dim_battery_material", "ods_dim_battery_material", "dwd_dim_battery_material",
        "dim_charging_operator", "ods_dim_charging_operator", "dwd_dim_charging_operator",
        "fact_global_ev_sales_yearly", "ods_fact_global_ev_sales_yearly", "dwd_global_ev_sales_yearly", "dws_global_ev_sales_yearly", "ads_global_ev_sales_yearly",
        "fact_global_ev_stock_yearly", "ods_fact_global_ev_stock_yearly", "dwd_global_ev_stock_yearly", "dws_global_ev_stock_yearly", "ads_global_ev_stock_yearly",
        "fact_battery_production_monthly", "ods_fact_battery_production_monthly", "dwd_battery_production_monthly", "dws_battery_production_monthly", "ads_battery_production_monthly",
        "fact_vehicle_production_province_monthly", "ods_fact_vehicle_production_province_monthly", "dwd_vehicle_production_province_monthly", "dws_vehicle_production_province_monthly", "ads_vehicle_production_province_monthly",
        "fact_charging_operator_monthly", "ods_fact_charging_operator_monthly", "dwd_charging_operator_monthly", "dws_charging_operator_monthly", "ads_charging_operator_monthly",
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
    dialect: str = "mysql"

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
        expression = self._normalize_date_filters(expression)
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

    def _normalize_date_filters(self, expression: exp.Expression) -> exp.Expression:
        def rewrite(node: exp.Expression) -> exp.Expression:
            if (
                isinstance(node, exp.Between)
                and _is_data_month_column(node.this)
                and (
                    _is_date_expression(node.args.get("low"))
                    or _is_date_expression(node.args.get("high"))
                )
            ):
                updated = node.copy()
                updated.set("this", _cast_as_date(node.this))
                return updated

            if isinstance(node, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)):
                left = node.this
                right = node.expression

                if _is_data_month_column(left) and _is_date_expression(right):
                    updated = node.copy()
                    updated.set("this", _cast_as_date(left))
                    return updated

                if _is_data_month_column(right) and _is_date_expression(left):
                    updated = node.copy()
                    updated.set("expression", _cast_as_date(right))
                    return updated

            return node

        return expression.transform(rewrite)

    def _with_limit(self, expression: exp.Expression) -> str:
        if expression.args.get("limit") is None:
            expression = expression.limit(self.default_limit)

        return expression.sql(dialect=self.dialect)


def guard_sql(sql: str, default_limit: int = 100) -> str:
    """使用默认表白名单校验并改写 SQL。"""
    return SQLGuard(default_limit=default_limit).validate_and_rewrite(sql)


def _normalize_name(name: str) -> str:
    return name.strip().lower()


def _is_data_month_column(expression: exp.Expression | None) -> bool:
    return isinstance(expression, exp.Column) and _normalize_name(expression.name) == "data_month"


def _is_date_expression(expression: exp.Expression | None) -> bool:
    return isinstance(expression, exp.Cast) and expression.to and expression.to.is_type("DATE")


def _cast_as_date(expression: exp.Expression) -> exp.Cast:
    return exp.Cast(this=expression.copy(), to=exp.DataType.build("DATE"))
