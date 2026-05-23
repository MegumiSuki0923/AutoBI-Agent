"""
inspect_raw_data.py — 原始 Excel 数据探查脚本（只读，不修改任何数据）

对 data/raw_data/ 下的 6 个 MVP 数据源做全面自动化探查。
不管原始文件是 .xlsx 还是 .xls（Datayes 宽表），读取后统一执行相同的质量检查：

  - 文件基本信息（格式、大小、Sheet 数量）
  - 列名、数据类型、空值数、唯一值数
  - 枚举值列（低基数文本列）
  - 数值列描述统计（min / max / mean / median / 零值比例）
  - 负值检测（行数 + 样例）
  - 重复行检测（按业务键）
  - 时间连续性检查（是否有缺月）
  - 日期格式一致性检查
  - 数据源特有的检查（充电设施省份脏数据、电池单位不一致）

使用方法：
    python scripts/inspect_raw_data.py

产出：
    控制台完整报告
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


# ────────────────────────────── 文件路径 ──────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw_data"


# ────────────────────────────── 数据源配置 ──────────────────────────────

DATA_SOURCES: dict[str, dict[str, Any]] = {
    "SRC001": {
        "file": "1汽车分品牌产销(95家车企，768个车型，201512-202210月度数据).xlsx",
        "topic": "汽车品牌车型产销",
        "format": "xlsx",
        "date_col": "数据日期",
        "biz_keys": ["制造厂", "车型", "统计类型", "数据日期"],
        "skip_subheader": False,
    },
    "SRC002": {
        "file": "2新能源汽车分厂商产销(207家厂商，201812-202210月度数据).xlsx",
        "topic": "新能源汽车分厂商产销",
        "format": "xlsx",
        "date_col": "数据日期",
        "biz_keys": ["厂商名称", "车型大类", "车型细分", "燃料类型", "数据日期"],
        "skip_subheader": True,  # 有双层表头，需跳过第二行
    },
    "SRC003": {
        "file": "3新能源汽车总体产销(201812-202210月度数据).xlsx",
        "topic": "新能源汽车总体产销",
        "format": "xlsx",
        "date_col": "数据日期",
        "biz_keys": ["车型大类", "车型细分", "燃料类型", "数据日期"],
        "skip_subheader": True,
    },
    "SRC004": {
        "file": "10国内充电设施数量（省份，月，201602-202302）.xls",
        "topic": "国内充电设施数量",
        "format": "xls",
        "date_col": "data_month",
        "biz_keys": None,  # 宽表转长表后再检查
    },
    "SRC005": {
        "file": "16动力电池装车量分车型（月，201909-202301，10个指标）.xls",
        "topic": "动力电池装车量分车型",
        "format": "xls",
        "date_col": "data_month",
        "biz_keys": None,
    },
    "SRC006": {
        "file": "17动力电池装车量分材料类型（月，201701-202301，10个指标）.xls",
        "topic": "动力电池装车量分材料类型",
        "format": "xls",
        "date_col": "data_month",
        "biz_keys": None,
    },
}

# 充电设施省份白名单
PROVINCE_WHITELIST = {
    "全国", "北京", "上海", "广东", "江苏", "山东", "安徽", "浙江",
    "湖北", "福建", "河南", "河北", "四川", "天津", "吉林",
}


# ────────────────────────────── 读取函数 ──────────────────────────────

def _read_standard_excel(file_path: Path, config: dict) -> pd.DataFrame:
    """读取标准格式 .xlsx 文件，返回 DataFrame"""
    df = pd.read_excel(file_path, engine="openpyxl")
    if config.get("skip_subheader"):
        df = df.dropna(subset=["序号"]).copy()
    return df


def _read_datayes_excel(file_path: Path) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    读取 Datayes 宽表 .xls 文件。
    返回 (数据 DataFrame, 指标名列表, 单位列表)
    """
    raw = pd.read_excel(file_path, header=None)
    metrics = raw.iloc[1, 1:].tolist()
    units = raw.iloc[3, 1:].tolist()

    data = raw.iloc[6:].copy()
    data.columns = ["data_month"] + metrics

    # 将指标列转为数值
    for col in metrics:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    return data, metrics, units


# ────────────────────────────── 统一质量检查 ──────────────────────────────

def check_column_info(df: pd.DataFrame) -> None:
    """列名、类型、空值、唯一值"""
    print(f"**行数**：{len(df)}，**列数**：{len(df.columns)}")
    print("")
    print("**列信息**：")
    print("")
    print("| 列名 | 类型 | 空值数 | 空值率 | 唯一值数 |")
    print("|------|------|--------|--------|----------|")
    for col in df.columns:
        dtype = str(df[col].dtype)
        null_count = int(df[col].isnull().sum())
        null_pct = null_count / len(df) * 100
        unique_count = df[col].nunique()
        print(f"| `{col}` | {dtype} | {null_count} | {null_pct:.1f}% | {unique_count} |")
    print("")


def check_enum_values(df: pd.DataFrame) -> None:
    """枚举值列（唯一值 ≤ 20 的文本列）"""
    enum_cols = [
        col for col in df.columns
        if df[col].nunique() <= 20 and df[col].dtype in ("object", "string")
    ]
    if not enum_cols:
        return

    print("**枚举值列**：")
    print("")
    for col in enum_cols:
        values = df[col].dropna().unique().tolist()
        print(f"- `{col}` ({len(values)} 种): {values}")
    print("")


def check_numeric_stats(df: pd.DataFrame) -> None:
    """数值列描述统计：min / max / mean / median / 零值"""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        return

    print("**数值列描述统计**：")
    print("")
    print("| 列名 | min | max | mean | median | 零值数 | 零值比例 |")
    print("|------|-----|-----|------|--------|--------|----------|")

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) == 0:
            print(f"| `{col}` | - | - | - | - | - | 全部为空 |")
            continue

        zero_count = int((series == 0).sum())
        zero_pct = zero_count / len(series) * 100
        print(
            f"| `{col}` | {series.min():,.2f} | {series.max():,.2f} | "
            f"{series.mean():,.2f} | {series.median():,.2f} | "
            f"{zero_count} | {zero_pct:.1f}% |"
        )
    print("")


def check_negative_values(df: pd.DataFrame, context_cols: list[str] | None = None) -> None:
    """数值列负值检测"""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    found = False

    for col in numeric_cols:
        neg_count = int((df[col] < 0).sum())
        if neg_count > 0:
            if not found:
                print("**⚠️ 负值检测**：")
                print("")
                found = True

            print(f"- `{col}`: {neg_count} 行负值 (最小值: {df[col].min():.2f})")

            if context_cols:
                samples = df[df[col] < 0].head(3)
                for _, row in samples.iterrows():
                    ctx_parts = []
                    for c in context_cols:
                        if c in df.columns and pd.notna(row.get(c)):
                            ctx_parts.append(f"{c}={row[c]}")
                    print(f"  - {', '.join(ctx_parts)} → {col}={row[col]}")

    if found:
        print("")


def check_date_format(df: pd.DataFrame, date_col: str) -> None:
    """日期列格式一致性"""
    if date_col not in df.columns:
        return

    series = df[date_col]
    raw_types = sorted({type(val).__name__ for val in series.dropna().head(100)})

    print(f"**日期格式检查** (`{date_col}`)：")
    print("")
    print(f"- 原始值类型：{raw_types}")

    parsed = pd.to_datetime(series, errors="coerce")
    original_null = int(series.isna().sum())
    parsed_null = int(parsed.isna().sum())
    parse_fail = parsed_null - original_null

    if parse_fail > 0:
        print(f"- ⚠️ 有 {parse_fail} 行无法解析为日期")
    else:
        print("- ✅ 全部可解析为日期")

    valid_dates = parsed.dropna()
    if len(valid_dates) > 0:
        day_values = sorted(valid_dates.dt.day.unique().tolist())
        if len(day_values) <= 5:
            print(f"- 日期中的「日」取值：{day_values}（判断是否月末对齐）")
        else:
            print(f"- 日期中的「日」取值较分散（{len(day_values)} 种），可能未统一月末")

    print("")


def check_time_continuity(df: pd.DataFrame, date_col: str) -> None:
    """月度时间序列连续性检查"""
    if date_col not in df.columns:
        return

    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if len(dates) < 2:
        return

    months = dates.dt.to_period("M").drop_duplicates().sort_values()
    full_range = pd.period_range(start=months.min(), end=months.max(), freq="M")
    missing = full_range.difference(months)

    print(f"**时间连续性检查** (`{date_col}`)：")
    print("")
    print(f"- 时间范围：{months.min()} ~ {months.max()}")
    print(f"- 覆盖月数：{len(months)}")
    print(f"- 应有月数：{len(full_range)}")

    if len(missing) > 0:
        missing_strs = [str(m) for m in missing[:10]]
        print(f"- ⚠️ 缺失月份 ({len(missing)} 个)：{missing_strs}")
        if len(missing) > 10:
            print(f"  - ... 及另外 {len(missing) - 10} 个")
    else:
        print("- ✅ 无缺月")

    print("")


def check_duplicates(df: pd.DataFrame, biz_keys: list[str], label: str = "") -> None:
    """按业务键检测重复行"""
    existing_cols = [c for c in biz_keys if c in df.columns]
    if len(existing_cols) != len(biz_keys):
        missing = set(biz_keys) - set(existing_cols)
        print(f"**重复行检测** {label}：跳过（缺少列 {missing}）")
        print("")
        return

    dup_mask = df.duplicated(subset=existing_cols, keep=False)
    dup_count = int(dup_mask.sum())

    print(f"**重复行检测** {label}：")
    print("")
    print(f"- 业务键：`{existing_cols}`")
    print(f"- 重复行数：{dup_count}")

    if dup_count > 0:
        dups = df[dup_mask]
        group_sizes = dups.groupby(existing_cols).size()
        print(f"- 重复组数：{len(group_sizes)}")
        print(f"- 每组行数分布：{group_sizes.value_counts().to_dict()}")

        if "车型细分" in dups.columns:
            print(f"- 重复行中 `车型细分` 分布：{dups['车型细分'].value_counts().to_dict()}")
            print(
                "  - 根因：原始数据对「货车/货车-专用货车」「客车/客车-城市客车」"
                "等父子分类产生了交叉组合"
            )

    print("")


def check_sample_data(df: pd.DataFrame, max_cols: int = 0) -> None:
    """打印前 3 行样例数据"""
    if max_cols > 0 and len(df.columns) > max_cols:
        sample = df.iloc[:3, :max_cols]
        label = f"前 3 行 × 前 {max_cols} 列"
    else:
        sample = df.head(3)
        label = "前 3 行"

    print(f"**样例数据（{label}）**：")
    print("")
    print("```")
    print(sample.to_string(index=False))
    print("```")
    print("")


# ────────────────────────────── 有效性：值域校验 ──────────────────────────────

# 比率类字段的合理范围定义
RATE_COLUMNS = {
    "当期同比(%)": (-500, 10000),    # 同比可能低于 -100%（如上年负值今年正值）
    "当期环比(%)": (-500, 10000),
    "累计同比(%)": (-500, 10000),
    "市占率(%)": (0, 100),           # 市占率必须在 0~100%
    "产量_1": (-500, 10000),         # SRC002/003 的同比列
    "产量_3": (-500, 10000),
    "销量_4": (-500, 10000),
    "销量_6": (-500, 10000),
}


def check_value_range(df: pd.DataFrame) -> None:
    """值域校验：比率字段是否在合理范围内，数值字段是否有离群值"""
    found = False

    # 1. 比率类字段范围检查
    for col, (low, high) in RATE_COLUMNS.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) == 0:
            continue

        out_of_range = series[(series < low) | (series > high)]
        if len(out_of_range) > 0:
            if not found:
                print("**⚠️ 值域校验**：")
                print("")
                found = True
            print(
                f"- `{col}`: {len(out_of_range)} 行超出合理范围 [{low}, {high}]"
                f" (实际范围: {series.min():.2f} ~ {series.max():.2f})"
            )

    # 2. 数值字段离群值检测（IQR 方法）
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    # 只检查核心数量字段，跳过比率和序号
    quantity_cols = [
        c for c in numeric_cols
        if c not in RATE_COLUMNS
        and c != "序号"
        and "率" not in c
        and "比" not in c
    ]

    for col in quantity_cols:
        series = df[col].dropna()
        if len(series) < 10:
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue

        upper_fence = q3 + 3 * iqr  # 使用 3 倍 IQR（极端离群值）
        extreme_count = int((series > upper_fence).sum())

        if extreme_count > 0 and extreme_count <= len(series) * 0.01:
            # 只报告极端少数的离群值（< 1%），避免误报
            if not found:
                print("**⚠️ 值域校验**：")
                print("")
                found = True
            print(
                f"- `{col}`: {extreme_count} 行极端离群值 "
                f"(阈值: {upper_fence:,.0f}, 最大值: {series.max():,.0f})"
            )

    if found:
        print("")


# ────────────────────────────── 一致性：跨列逻辑校验 ──────────────────────────────

# 定义「累计值 ≥ 当期值」的列对
CROSS_COLUMN_PAIRS = [
    ("当期值(辆)", "累计值(辆)"),                      # SRC001
    ("产量", "产量_2"),                                # SRC002/003: 当期产量 vs 累计产量
    ("销量", "销量_5"),                                # SRC002/003: 当期销量 vs 累计销量
]


def check_cross_column_consistency(df: pd.DataFrame) -> None:
    """跨列一致性：检查 累计值 ≥ 当期值 是否成立"""
    found = False

    for current_col, cumulative_col in CROSS_COLUMN_PAIRS:
        if current_col not in df.columns or cumulative_col not in df.columns:
            continue

        current = pd.to_numeric(df[current_col], errors="coerce")
        cumulative = pd.to_numeric(df[cumulative_col], errors="coerce")

        # 两列都非空的行
        mask = current.notna() & cumulative.notna()
        valid = mask.sum()
        if valid == 0:
            continue

        # 当期值 > 累计值 的异常行（排除负值冲销）
        violation = ((current > cumulative) & (current > 0) & mask)
        violation_count = int(violation.sum())

        if not found:
            print("**跨列一致性检查**（累计值 ≥ 当期值）：")
            print("")
            found = True

        if violation_count > 0:
            print(
                f"- ⚠️ `{current_col}` > `{cumulative_col}`: "
                f"{violation_count} 行违反 ({violation_count / valid * 100:.1f}%)"
            )
        else:
            print(f"- ✅ `{current_col}` ≤ `{cumulative_col}`: 全部通过 ({valid} 行)")

    if found:
        print("")


# ────────────────────────────── 规范性：字符串检查 ──────────────────────────────

def check_string_quality(df: pd.DataFrame) -> None:
    """字符串规范性：首尾空格、空字符串、异常长度"""
    text_cols = [c for c in df.columns if df[c].dtype in ("object", "string")]
    if not text_cols:
        return

    found = False

    for col in text_cols:
        series = df[col].dropna().astype(str)
        if len(series) == 0:
            continue

        # 首尾空格
        stripped = series.str.strip()
        space_count = int((series != stripped).sum())

        # 空字符串
        empty_count = int((stripped == "").sum())

        # 长度异常（超过均值 + 5 倍标准差）— 仅对高基数列检查（枚举列跳过）
        lengths = series.str.len()
        if lengths.std() > 0 and series.nunique() > 20:
            length_threshold = lengths.mean() + 5 * lengths.std()  # 5 倍标准差，避免中文名称误报
            long_count = int((lengths > length_threshold).sum())
        else:
            long_count = 0

        issues = []
        if space_count > 0:
            issues.append(f"首尾空格 {space_count} 行")
        if empty_count > 0:
            issues.append(f"空字符串 {empty_count} 行")
        if long_count > 0:
            issues.append(f"异常长文本 {long_count} 行 (阈值: {length_threshold:.0f} 字符)")

        if issues:
            if not found:
                print("**⚠️ 字符串规范性检查**：")
                print("")
                found = True
            print(f"- `{col}`: {'; '.join(issues)}")

    if not found:
        print("**字符串规范性检查**：✅ 全部通过")

    print("")


# ────────────────────────────── 数据源特有检查 ──────────────────────────────

def check_charging_province(metrics: list[str]) -> None:
    """SRC004 特有：检查充电设施列名中的非省份值"""
    suffixes: set[str] = set()
    for m in metrics:
        if isinstance(m, str) and "_" in m:
            parts = m.split("_")
            suffixes.add(parts[-1])

    non_province = suffixes - PROVINCE_WHITELIST
    if non_province:
        print(f"**⚠️ 列名后缀中的非省份值**：`{sorted(non_province)}`")
        print("  - `交流桩`、`直流桩`：按桩类型拆分的全国数据，不是省份")
        print("  - `同比`、`环比`：增速指标，不是省份")
        print("  - `合计`、`总计`：汇总行，不是省份")
        print("")


def check_unit_consistency(metrics: list[str], units: list[str]) -> None:
    """SRC005/006 特有：检查单位是否一致"""
    unique_units = sorted(set(u for u in units if isinstance(u, str)))
    print(f"**单位枚举**：{unique_units}")
    print("")

    if len(unique_units) > 1:
        print("**⚠️ 单位不一致**：")
        unit_map: dict[str, list[str]] = {}
        for m, u in zip(metrics, units):
            if isinstance(u, str):
                unit_map.setdefault(u, []).append(str(m))
        for unit, cols in unit_map.items():
            preview = cols[:3]
            suffix = "..." if len(cols) > 3 else ""
            print(f"  - `{unit}`: {len(cols)} 列 → {preview}{suffix}")
        print("")


# ────────────────────────────── 探查入口 ──────────────────────────────

def inspect_source(source_id: str, config: dict) -> None:
    """对一个数据源执行完整探查"""
    file_path = RAW_DATA_DIR / config["file"]

    if not file_path.exists():
        print(f"### {source_id}: ❌ 文件不存在 `{config['file']}`")
        print("")
        return

    fmt = config["format"]
    date_col = config["date_col"]

    # ── 文件基本信息 ──
    print(f"### {source_id}: {config['topic']}")
    print(f"- 文件：`{file_path.name}`")
    print(f"- 格式：`{fmt}`")
    print(f"- 大小：{file_path.stat().st_size / 1024:.0f} KB")

    # Sheet 信息
    if fmt == "xlsx":
        xls = pd.ExcelFile(file_path, engine="openpyxl")
    else:
        xls = pd.ExcelFile(file_path)
    sheets = xls.sheet_names
    print(f"- Sheet：{len(sheets)} 个" + (f" {sheets}" if len(sheets) > 1 else ""))

    # Datayes 宽表额外说明
    if fmt == "xls":
        print(f"- 结构：Datayes 元数据宽表（前 6 行为元数据，第 7 行起为数据）")
    print("")

    # ── 读取数据 ──
    metrics = None
    units = None

    if fmt == "xlsx":
        df = _read_standard_excel(file_path, config)
    else:
        df, metrics, units = _read_datayes_excel(file_path)

    # ── Datayes 文件专属：指标列名清单 ──
    if metrics is not None:
        print(f"**指标列数**：{len(metrics)}")
        print("")
        print("**指标列名**：")
        print("")
        for i, m in enumerate(metrics):
            u = units[i] if units and i < len(units) else "?"
            print(f"- 列{i + 1}: `{m}` [{u}]")
        print("")

    # ── 以下为统一质量检查，所有数据源执行相同逻辑 ──

    # 1. 完整性：列信息（类型、空值、唯一值）
    check_column_info(df)

    # 2. 有效性：枚举值列
    check_enum_values(df)

    # 3. 有效性：数值列描述统计
    check_numeric_stats(df)

    # 4. 有效性：负值检测
    text_cols = [c for c in df.columns if df[c].dtype in ("object", "string")][:3]
    check_negative_values(df, context_cols=text_cols)

    # 5. 有效性：值域校验（比率范围 + 离群值）
    check_value_range(df)

    # 6. 一致性：跨列逻辑校验（累计值 ≥ 当期值）
    check_cross_column_consistency(df)

    # 7. 规范性：字符串质量检查（空格、空值、长度）
    check_string_quality(df)

    # 8. 时效性：日期格式检查
    check_date_format(df, date_col)

    # 9. 时效性：时间连续性
    check_time_continuity(df, date_col)

    # 10. 唯一性：重复行检测
    biz_keys = config.get("biz_keys")
    if biz_keys:
        check_duplicates(df, biz_keys, label=f"({source_id})")

    # ── 数据源特有检查 ──

    if source_id == "SRC004" and metrics:
        check_charging_province(metrics)

    if source_id in ("SRC005", "SRC006") and metrics and units:
        check_unit_consistency(metrics, units)

    # ── 样例数据 ──
    max_cols = 5 if len(df.columns) > 8 else 0
    check_sample_data(df, max_cols=max_cols)

    print("---")
    print("")


# ────────────────────────────── 主函数 ──────────────────────────────

def main() -> None:
    print("# AutoBI Agent 原始数据探查报告")
    print("")
    print(f"数据目录：`{RAW_DATA_DIR}`")
    print(f"MVP 数据源：{len(DATA_SOURCES)} 个")
    print("")
    print("---")
    print("")

    for source_id, config in DATA_SOURCES.items():
        inspect_source(source_id, config)

    # 汇总
    print("## 探查问题汇总")
    print("")
    print("| # | 数据源 | 问题 | 严重程度 | 清洗建议 |")
    print("|---|--------|------|----------|----------|")
    print("| 1 | SRC001 | `stat_type` 包含「出口」，文档中未定义 | 中 | 保留数据，在数据字典中补充说明 |")
    print("| 2 | SRC001 | `current_units` 有负值（退货冲销） | 低 | 保留，在数据字典中说明含义 |")
    print("| 3 | SRC001 | `current_units` 大量零值 | 信息 | 正常，部分车型特定月份无产销 |")
    print("| 4 | SRC002 | 业务键重复（货车/货车-专用货车、客车/客车-城市客车交叉组合） | 高 | 按序号保留首条 |")
    print("| 5 | SRC002 | `sales_current_units` 有负值 | 低 | 保留，同 SRC001 |")
    print("| 6 | SRC004 | `province` 列混入非省份值 | 高 | 拆分为省份维度和其他维度 |")
    print("| 7 | SRC005/006 | 单位混合（MWh vs GWh） | 中 | 统一为 MWh 或在清洗时标注 |")
    print("")


if __name__ == "__main__":
    main()
