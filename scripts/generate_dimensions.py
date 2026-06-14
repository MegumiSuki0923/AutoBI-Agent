"""
generate_dimensions.py — 维度表生成脚本

仅生成 7 张维度表 CSV，不重新清洗事实表。
依赖 clean_raw_data.py 中已有的事实表 CSV。

使用方法：
    python scripts/generate_dimensions.py

产出（data/cleaned/）：
    dim_time.csv
    dim_manufacturer.csv
    dim_vehicle_model.csv
    dim_province.csv
    dim_fuel_type.csv
    dim_battery_material.csv
    dim_charging_operator.csv
"""

from clean_raw_data import generate_all_dimensions, CLEANED_DIR


if __name__ == "__main__":
    print("开始生成维度表...\n")
    dim_counts = generate_all_dimensions()
    print(f"\n维度表生成完成，共 {sum(dim_counts.values())} 行数据写入 {CLEANED_DIR}")
