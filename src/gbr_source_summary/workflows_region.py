from __future__ import annotations

from pathlib import Path

import pandas as pd

from gbr_source_summary.comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)
from gbr_source_summary.workflows_basin import build_basin_scenario_comparison
from .export import ensure_output_dir
from .export_excel import export_tables_to_excel


def build_region_totals_from_basin_totals(
    basin_totals: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    """
    Build region totals by aggregating basin totals.

    Expected basin_totals columns:
    - Scenario
    - Region
    - Basin
    - Constituent
    - Units
    - value_column
    """
    required_cols = ["Scenario", "Region", "Constituent", "Units", value_column]
    missing = [c for c in required_cols if c not in basin_totals.columns]
    if missing:
        raise KeyError(
            f"Missing required columns in basin_totals for region aggregation: {missing}"
        )

    out = (
        basin_totals.groupby(
            ["Scenario", "Region", "Constituent", "Units"],
            dropna=False,
            as_index=False,
        )[value_column]
        .sum()
    )

    return out


def build_region_scenario_wide_tables(
    region_totals: pd.DataFrame,
    value_column: str,
) -> dict[str, pd.DataFrame]:
    """
    Pivot region totals to scenario-wide tables for comparison.

    Outputs:
    - base_wide
    - predev_wide
    - change_wide

    Each table has:
    index = Region
    columns = Constituent
    values = value_column
    """
    required_cols = ["Scenario", "Region", "Constituent", value_column]
    missing = [c for c in required_cols if c not in region_totals.columns]
    if missing:
        raise KeyError(
            f"Missing required columns in region_totals for wide pivot: {missing}"
        )

    base = region_totals.loc[region_totals["Scenario"] == "BASE"].copy()
    predev = region_totals.loc[region_totals["Scenario"] == "PREDEV"].copy()
    change = region_totals.loc[region_totals["Scenario"] == "CHANGE"].copy()

    index_cols = ["Region"]

    base_wide = base.pivot_table(
        index=index_cols,
        columns="Constituent",
        values=value_column,
        aggfunc="sum",
        fill_value=0.0,
    )

    predev_wide = predev.pivot_table(
        index=index_cols,
        columns="Constituent",
        values=value_column,
        aggfunc="sum",
        fill_value=0.0,
    )

    change_wide = change.pivot_table(
        index=index_cols,
        columns="Constituent",
        values=value_column,
        aggfunc="sum",
        fill_value=0.0,
    )

    base_wide.columns.name = None
    predev_wide.columns.name = None
    change_wide.columns.name = None

    return {
        "base_wide": base_wide,
        "predev_wide": predev_wide,
        "change_wide": change_wide,
    }


def build_region_scenario_comparison_from_basin_totals(
    basin_totals: pd.DataFrame,
    value_column: str,
) -> dict[str, pd.DataFrame]:
    """
    Build region scenario comparison outputs from a basin totals dataframe.
    """
    region_totals = build_region_totals_from_basin_totals(
        basin_totals=basin_totals,
        value_column=value_column,
    )

    wide = build_region_scenario_wide_tables(
        region_totals=region_totals,
        value_column=value_column,
    )

    anthropogenic = calc_anthropogenic(
        wide["base_wide"],
        wide["predev_wide"],
    )

    reduction = calc_reduction(
        wide["base_wide"],
        wide["change_wide"],
    )

    percent_reduction = calc_percent_reduction(
        wide["base_wide"],
        wide["predev_wide"],
        wide["change_wide"],
    )

    return {
        "region_totals": region_totals,
        "base_wide": wide["base_wide"],
        "predev_wide": wide["predev_wide"],
        "change_wide": wide["change_wide"],
        "anthropogenic": anthropogenic,
        "reduction": reduction,
        "percent_reduction": percent_reduction,
    }


def build_region_scenario_comparison(
    cfg,
    basin_scale: str = "48",
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    reporting_units: str = "raw",
) -> dict[str, pd.DataFrame]:
    """
    Build region scenario comparison by first generating basin outputs,
    then rolling basin totals up to region totals.

    Returns:
    - basin_fu_loads
    - basin_totals
    - region_totals
    - base_wide
    - predev_wide
    - change_wide
    - anthropogenic
    - reduction
    - percent_reduction
    """
    basin_outputs = build_basin_scenario_comparison(
        cfg=cfg,
        basin_scale=basin_scale,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        reporting_units=reporting_units,
    )

    basin_totals = basin_outputs["compare_ready"]

    region_outputs = build_region_scenario_comparison_from_basin_totals(
        basin_totals=basin_totals,
        value_column=value_column,
    )

    return {
        "basin_fu_loads": basin_outputs["basin_loads"],
        "basin_totals": basin_totals,
        "region_totals": region_outputs["region_totals"],
        "base_wide": region_outputs["base_wide"],
        "predev_wide": region_outputs["predev_wide"],
        "change_wide": region_outputs["change_wide"],
        "anthropogenic": region_outputs["anthropogenic"],
        "reduction": region_outputs["reduction"],
        "percent_reduction": region_outputs["percent_reduction"],
    }


def run_region_summary(
    cfg,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    basin_scale: str = "48",
    regions: list[str] | None = None,
    bundle_dirs: dict[str, Path] | None = None,
) -> dict[str, object]:
    """
    Export region scenario comparison outputs.

    Notes
    -----
    `process_model` is accepted for interface consistency with the bundle runner
    but is not used here.
    """
    out_dir = ensure_output_dir(output_dir)

    result = build_region_scenario_comparison(
        cfg=cfg,
        basin_scale=basin_scale,
        regions=regions if regions is not None else getattr(cfg, "regions", None),
        constituents=constituents,
        value_column=value_column,
        reporting_units="report_card" if units == "report" else "raw",
    )

    files: dict[str, Path] = {}

    # Long tables
    region_totals_csv = out_dir / "region_totals.csv"
    basin_totals_csv = out_dir / "region_source_basin_totals.csv"
    basin_fu_loads_csv = out_dir / "region_source_basin_fu_loads.csv"

    result["region_totals"].to_csv(region_totals_csv, index=False)
    result["basin_totals"].to_csv(basin_totals_csv, index=False)
    result["basin_fu_loads"].to_csv(basin_fu_loads_csv, index=False)

    files["region_output_csv"] = region_totals_csv
    files["region_basin_totals_csv"] = basin_totals_csv
    files["region_basin_fu_loads_csv"] = basin_fu_loads_csv

    # Wide tables
    workbook_path = out_dir / "region_summary.xlsx"
    export_tables_to_excel(
        tables={
            "region_totals": result["region_totals"],
            "basin_totals": result["basin_totals"],
            "basin_fu_loads": result["basin_fu_loads"],
            "base_wide": result["base_wide"].reset_index(),
            "predev_wide": result["predev_wide"].reset_index(),
            "change_wide": result["change_wide"].reset_index(),
            "anthropogenic": result["anthropogenic"].reset_index(),
            "reduction": result["reduction"].reset_index(),
            "percent_reduction": result["percent_reduction"].reset_index(),
        },
        output_path=workbook_path,
        index=False,
    )
    files["region_summary_workbook"] = workbook_path

    return {
        "region_totals": result["region_totals"],
        "basin_totals": result["basin_totals"],
        "basin_fu_loads": result["basin_fu_loads"],
        "base_wide": result["base_wide"],
        "predev_wide": result["predev_wide"],
        "change_wide": result["change_wide"],
        "anthropogenic": result["anthropogenic"],
        "reduction": result["reduction"],
        "percent_reduction": result["percent_reduction"],
        "files": files,
    }