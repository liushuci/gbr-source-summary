from pathlib import Path

from gbr_source_summary import GBRConfig, build_fu_scenario_comparison

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = build_fu_scenario_comparison(
    cfg=cfg,
    region="CY",
)

print("BASE")
print(result["base"].head())
print()

print("ANTHROPOGENIC")
print(result["anthropogenic"].head())
print()

print("PERCENT REDUCTION")
print(result["percent_reduction"].head())

print("REDUCTION")
print(result["reduction"].head())