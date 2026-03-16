from pathlib import Path

from gbr_source_summary import GBRConfig
from gbr_source_summary.io import load_reg_contributor_data_grid_with_lut
from gbr_source_summary.summary_flow import build_fu_flow_summary, build_basin_flow_summary

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

df = load_reg_contributor_data_grid_with_lut(cfg, region="CY", model="BASE")

# Replace with the actual flow value column if needed
value_column = "LoadToRegExport (kg)"

fu_flow = build_fu_flow_summary(df, value_column=value_column)
basin_flow = build_basin_flow_summary(df, value_column=value_column)

print("FU flow summary")
print(fu_flow.head())
print()
print("Basin flow summary")
print(basin_flow.head())