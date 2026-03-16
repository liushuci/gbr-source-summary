from pathlib import Path

from gbr_source_summary import GBRConfig
from gbr_source_summary.workflows_process import build_process_export_summaries

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

basin_by_region, region_by_region, combined = build_process_export_summaries(
    cfg=cfg,
    model="BASE",
    region="CY",
    units="report",
)

print("\nAvailable CY constituents:")
print(list(region_by_region["CY"].keys()))

print("\nCY FS process summary:")
print(region_by_region["CY"]["FS"].head())

print("\nCombined DIN process summary:")
print(combined["DIN"].head())