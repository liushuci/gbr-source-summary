"""
Process report workflow for gbr_source_summary.
"""

from __future__ import annotations

from pathlib import Path

from .config import GBRConfig
from .export import ensure_output_dir, export_constituent_tables_csv
from .export_excel import export_tables_to_excel
from .units import label_for_units
from .workflows_process import build_process_export_summaries


def run_process_report(
    cfg: GBRConfig,
    output_dir: str | Path,
    model: str = "BASE",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
    export_region_tables: bool = True,
    export_combined_tables: bool = True,
    export_excel_workbook: bool = True,
) -> dict[str, object]:
    """
    Run the process export workflow and export results.
    """
    out_dir = ensure_output_dir(output_dir)
    unit_label = label_for_units(units)
    model_lower = model.lower()

    basin_by_region, region_by_region, combined = build_process_export_summaries(
        cfg=cfg,
        model=model,
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    files: dict[str, Path] = {}

    if export_region_tables:
        regions_dir = out_dir / "regions"
        regions_dir.mkdir(parents=True, exist_ok=True)

        for reg, summary_dict in region_by_region.items():
            export_constituent_tables_csv(
                summary_dict,
                regions_dir,
                prefix=f"{reg}_{model_lower}_",
                suffix=f"_{unit_label}",
                index=True,   # keep Process row names
            )

        files["regions_dir"] = regions_dir

    if export_combined_tables:
        export_constituent_tables_csv(
            combined,
            out_dir,
            prefix=f"{model_lower}_process_",
            suffix=f"_{unit_label}",
            index=True,   # keep Process row names
        )

        for constituent in combined:
            files[f"{constituent}_csv"] = (
                out_dir / f"{model_lower}_process_{constituent}_{unit_label}.csv"
            )

    if export_excel_workbook:
        workbook_path = out_dir / f"process_report_{model_lower}_{unit_label}.xlsx"
        export_tables_to_excel(
            tables=combined,
            output_path=workbook_path,
            index=True,   # keep Process row names in workbook too
        )
        files["workbook"] = workbook_path

    return {
        "basin_by_region": basin_by_region,
        "region_by_region": region_by_region,
        "combined": combined,
        "files": files,
    }


def run_all_gbr_process_reports(
    cfg: GBRConfig,
    output_dir: str | Path,
    model: str = "BASE",
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
    export_region_tables: bool = True,
    export_combined_tables: bool = True,
    export_excel_workbook: bool = True,
) -> dict[str, object]:
    """
    Run process reports for all configured GBR regions in one call.
    """
    result = run_process_report(
        cfg=cfg,
        output_dir=output_dir,
        model=model,
        regions=cfg.regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        export_region_tables=export_region_tables,
        export_combined_tables=export_combined_tables,
        export_excel_workbook=export_excel_workbook,
    )

    result["regions_run"] = list(cfg.regions)
    return result