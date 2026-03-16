from pathlib import Path

from gbr_source_summary import (
    GBRConfig,
    build_fu_basin_scenario_comparison,
    flatten_basin_tables,
)

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = build_fu_basin_scenario_comparison(
    cfg=cfg,
    region="CY",
    units="report",
)

print("\nAvailable CY basins:")
print(list(result["base_basin"]["CY"].keys())[:10])

first_basin = list(result["base_basin"]["CY"].keys())[0]

print(f"\nBASE table for basin: {first_basin}")
print(result["base_basin"]["CY"][first_basin].head())

print(f"\nANTHROPOGENIC table for basin: {first_basin}")
print(result["anthropogenic_basin"]["CY"][first_basin].head())

flat = flatten_basin_tables(result["base_basin"])
print("\nFlattened basin table preview:")
print(flat.head())