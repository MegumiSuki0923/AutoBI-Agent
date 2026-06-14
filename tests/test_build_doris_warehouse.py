from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts import build_doris_warehouse


class FakeCursor:
    def __init__(self):
        self.statements: list[str] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.statements.append(str(sql))

    def executemany(self, sql, params):
        rows = list(params)
        self.executemany_calls.append((str(sql), rows))


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


def _write_minimal_cleaned_csvs(cleaned_dir: Path) -> None:
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    rows_by_table = {
        "dim_data_source": [
            {
                "source_id": 1,
                "source_name": "汽车品牌车型产销",
                "file_name": "sample.xlsx",
                "target_table": "fact_vehicle_prod_sales_monthly",
            }
        ],
        "fact_vehicle_prod_sales_monthly": [
            {
                "record_id": 1,
                "source_id": 1,
                "manufacturer_name": "特斯拉上海",
                "model_name": "Model3",
                "stat_type": "销量",
                "data_month": "2022-12-31",
                "current_units": 1000.0,
                "yoy_rate": 0.1,
            }
        ],
        "fact_nev_manufacturer_monthly": [
            {
                "record_id": 1,
                "source_id": 1,
                "manufacturer_name": "比亚迪",
                "vehicle_category": "总计",
                "vehicle_segment": "总计",
                "fuel_type": "总计",
                "data_month": "2022-12-31",
                "production_current_units": 1800000.0,
                "sales_current_units": 1860000.0,
            }
        ],
        "fact_nev_overall_monthly": [
            {
                "record_id": 1,
                "source_id": 1,
                "vehicle_category": "总计",
                "vehicle_segment": "总计",
                "fuel_type": "总计",
                "data_month": "2022-12-31",
                "production_current_units": 1900000.0,
                "sales_current_units": 2000000.0,
            }
        ],
        "fact_charging_infrastructure_monthly": [
            {
                "record_id": 1,
                "source_id": 1,
                "province": "广东",
                "data_month": "2022-12-31",
                "metric_name": "公共充电桩数量",
                "metric_value": 100.0,
                "unit": "万台",
            }
        ],
        "fact_battery_installation_monthly": [
            {
                "record_id": 1,
                "source_id": 1,
                "dimension_type": "material_type",
                "dimension_value": "磷酸铁锂",
                "data_month": "2022-12-31",
                "metric_name": "装车量",
                "metric_value": 183.8,
                "unit": "GWh",
            }
        ],
    }

    for table_name, rows in rows_by_table.items():
        pd.DataFrame(rows).to_csv(cleaned_dir / f"{table_name}.csv", index=False)


def test_build_doris_warehouse_loads_ods_and_creates_serving_layers(tmp_path, monkeypatch):
    cleaned_dir = tmp_path / "cleaned"
    _write_minimal_cleaned_csvs(cleaned_dir)
    cursor = FakeCursor()

    monkeypatch.setattr(
        build_doris_warehouse,
        "_connect",
        lambda **kwargs: FakeConnection(cursor),
    )

    counts = build_doris_warehouse.build_warehouse(cleaned_dir=cleaned_dir)

    assert counts == {
        f"ods_{table_name}": 1 for table_name in build_doris_warehouse.SOURCE_TABLES
    }

    ddl = "\n".join(cursor.statements).lower()
    for table_name in build_doris_warehouse.SOURCE_TABLES:
        assert f"ods_{table_name}" in ddl

    for layer_table in [
        "dwd_vehicle_prod_sales_monthly",
        "dws_nev_manufacturer_sales_monthly",
        "ads_nev_manufacturer_sales_rank",
        "ads_nev_penetration_trend",
        "ads_charging_facility_province_distribution",
        "ads_battery_material_share",
    ]:
        assert layer_table in ddl

    assert cursor.executemany_calls
