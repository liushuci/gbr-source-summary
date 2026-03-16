from pathlib import Path

from gbr_source_summary import (
    GBRConfig,
    build_fu_scenario_comparison,
    check_no_negative_values,
    check_anthropogenic_consistency,
    check_reduction_consistency,
    check_percent_reduction_bounds,
)

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = build_fu_scenario_comparison(cfg=cfg, region="CY")

print("Negative values in BASE")
print(check_no_negative_values(result["base"]))

print("\nAnthropogenic consistency")
print(check_anthropogenic_consistency(
    result["base"], result["predev"], result["anthropogenic"]
))

print("\nReduction consistency")
print(check_reduction_consistency(
    result["base"], result["change"], result["reduction"]
))

print("\nPercent reduction out of bounds")
print(check_percent_reduction_bounds(result["percent_reduction"]))