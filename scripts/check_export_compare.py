from pathlib import Path

from gbr_source_summary import (
    GBRConfig,
    build_fu_scenario_comparison,
    export_table_csv,
)

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = build_fu_scenario_comparison(
    cfg=cfg,
    region="CY",
)

output_dir = Path("outputs") / "CY"
export_table_csv(result["base"], output_dir / "base_fu.csv")
export_table_csv(result["anthropogenic"], output_dir / "anthropogenic_fu.csv")
export_table_csv(result["percent_reduction"], output_dir / "percent_reduction_fu.csv")

print("Exported:")
print(output_dir / "base_fu.csv")
print(output_dir / "anthropogenic_fu.csv")
print(output_dir / "percent_reduction_fu.csv")