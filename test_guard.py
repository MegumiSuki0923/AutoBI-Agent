from app.services.sql_guard import guard_sql

sql = "SELECT SUM(CASE WHEN fuel_type = '纯电动' THEN sales_sales_units ELSE 0 END) / NULLIF(SUM(sales_sales_units), 0) AS bev_share, SUM(CASE WHEN fuel_type = '插电式混合动力' THEN sales_sales_units ELSE 0 END) / NULLIF(SUM(sales_sales_units), 0) AS phev_share FROM dws_nev_market_monthly WHERE vehicle_category = '总计' AND vehicle_segment = '总计' AND fuel_type IN ('纯电动', '插电式混合动力') AND data_month >= '2022-01-01' AND data_month < '2023-01-01' LIMIT 1"

try:
    rewritten = guard_sql(sql)
    print("Original:", sql)
    print("Rewritten:", rewritten)
except Exception as e:
    print("Error:", e)
