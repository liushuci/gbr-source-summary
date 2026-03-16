from pathlib import Path

from gbr_source_summary import GBRConfig
from gbr_source_summary.workflows_flow import build_flow_summaries

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

fu_by_region, basin_by_region, combined_fu, combined_basin = build_flow_summaries(
    cfg=cfg,
    model="BASE",
    region="CY",
    value_column="LoadToRegExport (kg)",
    units="GL/yr",
)

print("FU flow by region")
print(fu_by_region["CY"])

print(basin_by_region["CY"])
print()
print("Combined FU flow")
print(combined_fu.head())