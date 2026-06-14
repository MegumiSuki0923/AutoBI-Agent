import pandas as pd
import altair as alt

def _build_pie_chart(df, x_axis, y_axis, title):
    chart_df = df[[x_axis, y_axis]].copy()
    chart_df[y_axis] = pd.to_numeric(chart_df[y_axis], errors="coerce")
    return (
        alt.Chart(chart_df)
        .mark_arc()
        .encode(
            theta=alt.Theta(f"{y_axis}:Q", title=y_axis),
            color=alt.Color(f"{x_axis}:N", title=x_axis),
            tooltip=[x_axis, y_axis],
        )
        .properties(title=title)
    )

df = pd.DataFrame({"pure_ev_ratio": [0.78], "phev_ratio": [0.22]})
x_axis = None
y_axes = ["pure_ev_ratio", "phev_ratio"]
title = "Test Pie"

if not x_axis or x_axis not in df.columns:
    if len(y_axes) > 1 and len(df) == 1:
        df = df.melt(value_vars=y_axes, var_name="metric", value_name="value")
        x_axis = "metric"
        y_axes = ["value"]
    else:
        print("饼图缺少分类字段或数值字段。")

try:
    chart = _build_pie_chart(df, x_axis, y_axes[0], title)
    chart_json = chart.to_json()
    print("SUCCESS")
except Exception as e:
    print("ERROR:", e)
