from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from app.schemas import ChartSuggestion


@dataclass(frozen=True)
class FieldProfile:
    name: str
    kind: str


class ChartService:
    """
    基于字段类型和用户问题意图推荐图表类型。

    当前支持：
    - line: 时间序列趋势
    - bar: 分类对比 / 排名
    - stacked_bar: 结构、占比、构成类问题
    - metric: 单指标结果
    """

    TIME_KEYWORDS = {
        "date",
        "month",
        "year",
        "time",
        "day",
        "weekly",
        "monthly",
        "yearly",
        "daily",
        "data_month",
        "日期",
        "月份",
        "月度",
        "年份",
        "时间",
    }
    NUMERIC_KEYWORDS = {
        "count",
        "sum",
        "total",
        "sales",
        "volume",
        "amount",
        "rate",
        "ratio",
        "units",
        "gwh",
        "value",
        "val",
        "num",
        "number",
        "quantity",
        "数量",
        "销量",
        "产量",
        "金额",
        "占比",
        "比例",
        "渗透率",
        "装车量",
    }
    TREND_KEYWORDS = {"趋势", "走势", "变化", "月度", "年度", "同比", "环比", "增长"}
    STRUCTURE_KEYWORDS = {"结构", "占比", "构成", "分布", "分类", "组成", "不同类型"}
    RANKING_KEYWORDS = {"排名", "排行", "top", "最高", "最低", "前"}
    METRIC_KEYWORDS = {"多少", "总量", "合计", "总计", "平均", "均值", "指标"}

    def recommend_chart(
        self,
        question: str,
        columns: List[str],
        rows: List[List[Any]],
    ) -> ChartSuggestion:
        profiles = self._infer_fields(columns, rows)
        time_fields = [field.name for field in profiles if field.kind == "time"]
        numeric_fields = [field.name for field in profiles if field.kind == "numeric"]
        category_fields = [field.name for field in profiles if field.kind == "category"]

        if not rows:
            return ChartSuggestion(
                chart_type="line" if time_fields and numeric_fields else "bar",
                x_axis=self._pick_x_axis(time_fields, category_fields, columns),
                y_axes=numeric_fields[:1] or columns[:1],
                title=self._build_title(question, "空结果"),
            )

        if self._should_use_metric(question, rows, numeric_fields):
            y_axis = numeric_fields[:1] or columns[:1]
            return ChartSuggestion(
                chart_type="metric",
                x_axis=None,
                y_axes=y_axis,
                title=self._build_title(question, "指标卡"),
            )

        if self._should_use_stacked_bar(question, time_fields, numeric_fields, category_fields):
            return ChartSuggestion(
                chart_type="stacked_bar",
                x_axis=self._pick_x_axis(time_fields, category_fields, columns),
                y_axes=numeric_fields,
                title=self._build_title(question, "结构"),
            )

        if time_fields and numeric_fields and self._has_intent(question, self.TREND_KEYWORDS):
            return ChartSuggestion(
                chart_type="line",
                x_axis=time_fields[0],
                y_axes=numeric_fields,
                title=self._build_title(question, "趋势"),
            )

        if time_fields and numeric_fields:
            return ChartSuggestion(
                chart_type="line",
                x_axis=time_fields[0],
                y_axes=numeric_fields,
                title=self._build_title(question, "趋势"),
            )

        if category_fields and numeric_fields:
            return ChartSuggestion(
                chart_type="bar",
                x_axis=category_fields[0],
                y_axes=numeric_fields[:1],
                title=self._build_title(question, "对比"),
            )

        return ChartSuggestion(
            chart_type="metric",
            x_axis=None,
            y_axes=numeric_fields[:1] or columns[:1],
            title=self._build_title(question, "指标卡"),
        )

    def _infer_fields(self, columns: List[str], rows: List[List[Any]]) -> List[FieldProfile]:
        profiles = []
        for index, column in enumerate(columns):
            values = [row[index] for row in rows if index < len(row)]
            if self._is_time_field(column, values):
                kind = "time"
            elif self._is_numeric_field(column, values):
                kind = "numeric"
            else:
                kind = "category"
            profiles.append(FieldProfile(name=column, kind=kind))
        return profiles

    def _is_time_field(self, column: str, values: List[Any]) -> bool:
        lowered = column.lower()
        tokens = lowered.split("_")

        # 1. 检查数据值：如果全是非空且符合日期格式，那一定是时间字段
        non_empty = [value for value in values if value is not None and value != ""]
        if non_empty and all(self._is_date_like(v) for v in non_empty):
            return True

        # 2. 根据列名做规则匹配
        last_token = tokens[-1] if tokens else ""
        
        # 常见的时间后缀指示词
        is_time_suffix = last_token in {"date", "time", "month", "year", "day", "日期", "时间", "月份", "年份"}
        # 显式排除包含数值关键字的后缀/复合词，比如月度销量 monthly_sales（虽然含有 month 但以 sales 结尾，属于数值）
        # 以及 sales_date 等虽然含有 sales 但以 date 结尾，属于时间
        is_time_name = (lowered == "data_month") or (
            is_time_suffix and not any(t in self.NUMERIC_KEYWORDS for t in tokens[:-1])
        )
        if is_time_name:
            return True

        # 含有时间词且完全没有数值词
        has_time_token = any(t in self.TIME_KEYWORDS for t in tokens)
        has_numeric_token = any(t in self.NUMERIC_KEYWORDS for t in tokens)
        if has_time_token and not has_numeric_token:
            return True

        return False

    def _is_numeric_field(self, column: str, values: List[Any]) -> bool:
        lowered = column.lower()
        tokens = lowered.split("_")

        # 含有数值词且完全没有时间词（或者数值词属于末尾/复合词）
        has_numeric_token = any(t in self.NUMERIC_KEYWORDS for t in tokens)
        
        # 1. 检查数据值：如果全是非空且符合数字格式
        non_empty = [value for value in values if value is not None and value != ""]
        
        if has_numeric_token:
            return True

        if non_empty:
            if all(self._is_number_like(v) for v in non_empty):
                # 排除像 year, month 等纯数字时间列
                if any(t in {"year", "month", "day", "年份", "月份", "日期"} for t in tokens):
                    return False
                return True

        return False

    def _is_date_like(self, value: Any) -> bool:
        if isinstance(value, datetime):
            return True
        if not isinstance(value, str):
            return False

        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
            try:
                datetime.strptime(text, fmt)
                return True
            except ValueError:
                continue
        return False

    def _is_number_like(self, value: Any) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return True
        if not isinstance(value, str):
            return False

        try:
            float(value.replace(",", "").strip())
            return True
        except ValueError:
            return False

    def _should_use_metric(
        self,
        question: str,
        rows: List[List[Any]],
        numeric_fields: List[str],
    ) -> bool:
        if not numeric_fields:
            return False
        return len(rows) == 1 and (
            self._has_intent(question, self.METRIC_KEYWORDS)
            or len(numeric_fields) == 1
        )

    def _should_use_stacked_bar(
        self,
        question: str,
        time_fields: List[str],
        numeric_fields: List[str],
        category_fields: List[str],
    ) -> bool:
        if not numeric_fields or not self._has_intent(question, self.STRUCTURE_KEYWORDS):
            return False
        return len(numeric_fields) > 1 or len(category_fields) >= 2 or bool(time_fields and category_fields)

    def _pick_x_axis(
        self,
        time_fields: List[str],
        category_fields: List[str],
        columns: List[str],
    ) -> Optional[str]:
        if time_fields:
            return time_fields[0]
        if category_fields:
            return category_fields[0]
        return columns[0] if columns else None

    def _has_intent(self, question: str, keywords: set[str]) -> bool:
        lowered = question.lower()
        return any(keyword in lowered or keyword in question for keyword in keywords)

    def _build_title(self, question: str, suffix: str) -> str:
        cleaned = question.strip().rstrip("？?。.")
        if not cleaned:
            return suffix
        if suffix in cleaned:
            return cleaned
        return f"{cleaned}{suffix}"
