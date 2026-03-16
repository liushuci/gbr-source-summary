from pathlib import Path

from gbr_source_summary import (
    GBRConfig,
    build_fu_scenario_comparison,
    export_tables_to_excel,
)

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = build_fu_scenario_comparison(
    cfg=cfg,
    region="CY",
)

tables = {
    "base": result["base"],
    "anthropogenic": result["anthropogenic"],
    "percent_reduction": result["percent_reduction"],
}

output = export_tables_to_excel(
    tables=tables,
    output_path=Path("outputs") / "CY" / "fu_comparison.xlsx",
)

print(f"Exported workbook: {output}")