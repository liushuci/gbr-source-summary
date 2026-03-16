from pathlib import Path

from gbr_source_summary import GBRConfig
from gbr_source_summary.io import load_source_outputs
from gbr_source_summary.naming import apply_constituent_name_standardisation
from gbr_source_summary.summary_fu import (
    build_basin_fu_summary,
    aggregate_region_fu_summary,
)

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
data = load_source_outputs(cfg, region="CY", model="BASE")

df = apply_constituent_name_standardisation(data["contributors_with_lut"])

basin_summary = build_basin_fu_summary(
    df=df,
    constituents=["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP"],
    fus_of_interest=cfg.fus_of_interest,
    value_column="LoadToRegExport (kg)",
    basin_column="Manag_Unit_48",
)

region_summary = aggregate_region_fu_summary(basin_summary)

print(list(basin_summary.keys())[:5])
print(region_summary.head())