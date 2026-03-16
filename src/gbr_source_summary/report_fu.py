"""
FU report workflow for gbr_source_summary.

This module provides high-level functions to:
- build FU scenario comparison tables
- export one CSV per region for each scenario
- export combined summary CSV tables
- export one Excel workbook with combined tables
- export a separate QA workbook

This mirrors the process report style and uses the FU scenario comparison
workflow as the core reporting backend.
"""

from __future__ import annotations

from pathlib import Path

from .config import GBRConfig
from .export import ensure_output_dir, export_region_tables_csv, export_report_tables
from .export_excel import export_tables_to_excel
from .qa_checks import (
    check_anthropogenic_consistency,
    check_no_negative_values,
    check_percent_reduction_bounds,
    check_reduction_consistency,
)
from .units import label_for_units
from .workflows_compare import build_fu_scenario_comparison


def run_fu_report(
    cfg: GBRConfig,
    output_dir: str | Path,
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
    export_region_tables: bool = True,
    export_combined_tables: bool = True,
    export_excel_workbook: bool = True,
    export_qa_workbook: bool = True,
) -> dict[str, object]:
    """
    Run the FU scenario comparison workflow and export results.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    output_dir : str | Path
        Folder for exported outputs.
    region : str | None
        Single region code.
    regions : list[str] | None
        Multiple region codes.
    constituents : list[str] | None
        Constituents to include.
    value_column : str
        Value column to summarise.
    units : str
        Output units. Examples:
        - "kg"
        - "t/yr"
        - "kt/yr"
        - "report"
    export_region_tables : bool
        Whether to export one CSV per region for each scenario.
    export_combined_tables : bool
        Whether to export combined summary CSV tables.
    export_excel_workbook : bool
        Whether to export one combined Excel workbook.
    export_qa_workbook : bool
        Whether to export a QA workbook.

    Returns
    -------
    dict[str, object]
        Result dictionary from build_fu_scenario_comparison, plus optional QA
        tables and a files dictionary.
    """
    out_dir = ensure_output_dir(output_dir)
    unit_label = label_for_units(units)

    result = build_fu_scenario_comparison(
        cfg=cfg,
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    files: dict[str, Path] = {}

    if export_region_tables:
        regions_dir = out_dir / "regions"

        export_region_tables_csv(
            result["predev_region"],
            regions_dir,
            suffix=f"_predev_{unit_label}",
        )
        export_region_tables_csv(
            result["base_region"],
            regions_dir,
            suffix=f"_base_{unit_label}",
        )
        export_region_tables_csv(
            result["change_region"],
            regions_dir,
            suffix=f"_change_{unit_label}",
        )

        files["regions_dir"] = regions_dir

    if export_combined_tables:
        tables = {
            "predev_fu": result["predev"],
            "base_fu": result["base"],
            "change_fu": result["change"],
            "anthropogenic_fu": result["anthropogenic"],
            "reduction_fu": result["reduction"],
            "percent_reduction_fu": result["percent_reduction"],
        }

        export_report_tables(
            tables=tables,
            output_dir=out_dir,
            units=units,
            export_csv=True,
        )

        for name in tables:
            files[f"{name}_csv"] = out_dir / f"{name}_{unit_label}.csv"

    if export_excel_workbook:
        workbook_tables = {
            "predev": result["predev"],
            "base": result["base"],
            "change": result["change"],
            "anthropogenic": result["anthropogenic"],
            "reduction": result["reduction"],
            "percent_reduction": result["percent_reduction"],
        }

        workbook_path = out_dir / f"fu_report_{unit_label}.xlsx"
        export_tables_to_excel(
            tables=workbook_tables,
            output_path=workbook_path,
        )
        files["workbook"] = workbook_path

    if export_qa_workbook:
        qa_tables = {
            "negative_values_base": check_no_negative_values(result["base"]),
            "anthropogenic_check": check_anthropogenic_consistency(
                result["base"],
                result["predev"],
                result["anthropogenic"],
            ),
            "reduction_check": check_reduction_consistency(
                result["base"],
                result["change"],
                result["reduction"],
            ),
            "percent_reduction_bounds": check_percent_reduction_bounds(
                result["percent_reduction"]
            ),
        }

        qa_workbook_path = out_dir / "fu_report_qa.xlsx"
        export_tables_to_excel(
            tables=qa_tables,
            output_path=qa_workbook_path,
        )

        result["qa"] = qa_tables
        files["qa_workbook"] = qa_workbook_path

    result["files"] = files
    return result


def run_all_gbr_fu_reports(
    cfg: GBRConfig,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
    export_region_tables: bool = True,
    export_combined_tables: bool = True,
    export_excel_workbook: bool = True,
    export_qa_workbook: bool = True,
) -> dict[str, object]:
    """
    Run FU reports for all configured GBR regions in one call.

    This is a thin wrapper around run_fu_report() using cfg.regions.
    """
    result = run_fu_report(
        cfg=cfg,
        output_dir=output_dir,
        regions=cfg.regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        export_region_tables=export_region_tables,
        export_combined_tables=export_combined_tables,
        export_excel_workbook=export_excel_workbook,
        export_qa_workbook=export_qa_workbook,
    )

    result["regions_run"] = list(cfg.regions)
    return result