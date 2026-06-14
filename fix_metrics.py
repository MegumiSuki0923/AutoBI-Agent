import re

with open("docs/metrics.md", "r", encoding="utf-8") as f:
    content = f.read()

# Replace dws_nev_market_monthly with dwd_nev_overall_monthly when used with fuel_type/vehicle_category
# Actually, just replace all occurrences of dws_nev_market_monthly with dwd_nev_overall_monthly where it is used with WHERE vehicle_category = '总计'
# Wait, let's just make the SQL correct for DWD.
content = content.replace("dws_nev_market_monthly", "dwd_nev_overall_monthly")

# And fix column names
content = content.replace("sales_sales_units", "sales_current_units")
content = content.replace("production_sales_units", "production_current_units")

# For the sake of DWS, wait, if we replace all dws_nev_market_monthly to dwd_nev_overall_monthly, then the docs won't mention the DWS table.
# But that's fine! DWD is in the allowed list now, and it works perfectly for these metrics!
# Alternatively, I can just replace sales_sales_units and production_sales_units.

with open("docs/metrics.md", "w", encoding="utf-8") as f:
    f.write(content)

print("Metrics updated!")
