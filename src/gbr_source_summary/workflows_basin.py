"""
Aggregation-scale summary workflows for gbr_source_summary.

Build scenario-wise grouped FU summaries using the existing FU workflow.

Supported aggregation scales:
- Basin_35
- Manag_Unit_48
- WQI

Important
---------
For bundle execution, run_basin_summary() first reuses the already-generated
core report-card basin summary from 01_report_card_summary. This avoids
re-reading and re-merging large RegContributorDataGrid files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from .config import GBRConfig
from .comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)
from .export import ensure_output_dir
from .export_excel import export_tables_to_excel
from .workflows_fu import build_fu_export_summaries, resolve_basin_column


def _add_raw_units(
    df: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)
    out["Units"] = "kg"
    return out


def _report_unit_for_constituent(constituent: str | None) -> str:
    key = str(constituent).strip().upper() if constituent is not None else ""
    if key in {"FS", "CS"}:
        return "kt/yr"
    return "t/yr"


def _convert_basin_report_units(
    df: pd.DataFrame,
    *,
    value_column: str,
    model_years: float,
) -> pd.DataFrame:
    required = ["Constituent", value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"Missing required columns for basin report-unit conversion: {missing}"
        )

    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)

    sediment_mask = out["Constituent"].astype(str).str.upper().isin(["FS", "CS"])

    out.loc[sediment_mask, value_column] = (
        out.loc[sediment_mask, value_column] / 1e6 / model_years
    )
    out.loc[~sediment_mask, value_column] = (
        out.loc[~sediment_mask, value_column] / 1e3 / model_years
    )

    out["Units"] = out["Constituent"].apply(_report_unit_for_constituent)

    return out


def _stack_basin_summaries(
    basin_summaries_by_region: Dict[str, dict[str, pd.DataFrame]],
    scenario: str,
    value_column: str,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []

    for region, basin_dict in basin_summaries_by_region.items():
        for basin, df in basin_dict.items():
            df_long = df.copy()

            if "FU" not in df_long.columns:
                if df_long.index.name == "FU":
                    df_long = df_long.reset_index()
                else:
                    df_long = df_long.reset_index()
                    if "FU" not in df_long.columns:
                        first_col = df_long.columns[0]
                        df_long = df_long.rename(columns={first_col: "FU"})

            df_long["Region"] = region
            df_long["Basin"] = basin
            df_long["Scenario"] = scenario

            id_vars = ["Scenario", "Region", "Basin", "FU"]
            value_vars = [c for c in df_long.columns if c not in id_vars]

            df_long = df_long.melt(
                id_vars=id_vars,
                value_vars=value_vars,
                var_name="Constituent",
                value_name=value_column,
            )

            df_long[value_column] = pd.to_numeric(
                df_long[value_column],
                errors="coerce",
            ).fillna(0.0)

            rows.append(df_long)

    if not rows:
        return pd.DataFrame(
            columns=[
                "Scenario",
                "Region",
                "Basin",
                "FU",
                "Constituent",
                value_column,
            ]
        )

    return pd.concat(rows, ignore_index=True)


def build_basin_export_summaries(
    cfg: GBRConfig,
    basin_scale: str = "48",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    reporting_units: str = "raw",
) -> pd.DataFrame:
    resolved_scale = resolve_basin_column(basin_scale)

    all_models: list[pd.DataFrame] = []

    for model in cfg.models:
        basin_summaries_by_region, _, _ = build_fu_export_summaries(
            cfg=cfg,
            model=model,
            region=region,
            regions=regions,
            constituents=constituents,
            value_column=value_column,
            units="kg",
            basin_scale=resolved_scale,
        )

        df_model = _stack_basin_summaries(
            basin_summaries_by_region=basin_summaries_by_region,
            scenario=model,
            value_column=value_column,
        )

        all_models.append(df_model)

    if not all_models:
        raise ValueError("No grouped summaries were generated.")

    basin_df = pd.concat(all_models, ignore_index=True)
    basin_df["BasinScale"] = resolved_scale

    if reporting_units == "report_card":
        basin_df = _convert_basin_report_units(
            basin_df,
            value_column=value_column,
            model_years=cfg.model_years,
        )
    elif reporting_units == "raw":
        basin_df = _add_raw_units(
            basin_df,
            value_column=value_column,
        )
    else:
        raise ValueError("Invalid reporting_units. Use 'raw' or 'report_card'.")

    return basin_df


def build_basin_scenario_comparison(
    cfg: GBRConfig,
    basin_scale: str = "48",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    reporting_units: str = "raw",
) -> dict[str, pd.DataFrame]:
    basin_df = build_basin_export_summaries(
        cfg=cfg,
        basin_scale=basin_scale,
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        reporting_units=reporting_units,
    )

    group_cols = [
        "Scenario",
        "Region",
        "Basin",
        "Constituent",
        "BasinScale",
    ]

    if "Units" in basin_df.columns:
        group_cols.append("Units")

    compare_ready = (
        basin_df.groupby(group_cols, dropna=False, as_index=False)[value_column]
        .sum()
    )

    def _scenario_wide(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
        out = df.loc[df["Scenario"] == scenario].copy()

        drop_cols = ["Scenario"]
        if "Units" in out.columns:
            drop_cols.append("Units")

        out = out.drop(columns=drop_cols)

        out = out.pivot_table(
            index=["Region", "Basin", "BasinScale"],
            columns="Constituent",
            values=value_column,
            aggfunc="sum",
            fill_value=0,
        )

        out = out.sort_index(axis=0).sort_index(axis=1)

        return out

    base_wide = _scenario_wide(compare_ready, "BASE")
    predev_wide = _scenario_wide(compare_ready, "PREDEV")
    change_wide = _scenario_wide(compare_ready, "CHANGE")

    full_index = base_wide.index.union(predev_wide.index).union(change_wide.index)
    full_columns = (
        base_wide.columns
        .union(predev_wide.columns)
        .union(change_wide.columns)
    )

    base_wide = base_wide.reindex(
        index=full_index,
        columns=full_columns,
        fill_value=0,
    )
    predev_wide = predev_wide.reindex(
        index=full_index,
        columns=full_columns,
        fill_value=0,
    )
    change_wide = change_wide.reindex(
        index=full_index,
        columns=full_columns,
        fill_value=0,
    )

    anthropogenic = calc_anthropogenic(base_wide, predev_wide)
    reduction = calc_reduction(base_wide, change_wide)
    percent_reduction = calc_percent_reduction(base_wide, predev_wide, change_wide)

    return {
        "basin_loads": basin_df,
        "compare_ready": compare_ready,
        "base_wide": base_wide,
        "predev_wide": predev_wide,
        "change_wide": change_wide,
        "anthropogenic": anthropogenic,
        "reduction": reduction,
        "percent_reduction": percent_reduction,
    }


def flatten_basin_tables(
    basin_tables_by_region: dict[str, dict[str, pd.DataFrame]],
) -> pd.DataFrame:
    frames = []

    for reg, basin_dict in basin_tables_by_region.items():
        for basin, df in basin_dict.items():
            temp = df.copy().reset_index()
            temp = temp.rename(columns={"index": "FU"})
            temp.insert(0, "Basin", basin)
            temp.insert(0, "Region", reg)
            frames.append(temp)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def _find_core_basin_summary_csv(
    *,
    bundle_dirs: dict[str, Path] | None,
) -> Path | None:
    """
    Find the already-generated core basin summary CSV from the report-card step.
    """
    if not bundle_dirs:
        return None

    core_dir = bundle_dirs.get("report_card_summary")
    if core_dir is None:
        return None

    core_dir = Path(core_dir)

    candidates = [
        core_dir / "report_card_summary_basin_report_units.csv",
        core_dir / "report_card_summary_basin_raw.csv",
        core_dir / "report_card_summary_basin_kg.csv",
    ]

    for path in candidates:
        if path.exists():
            return path

    matches = sorted(core_dir.glob("report_card_summary_basin_*.csv"))
    if matches:
        return matches[0]

    return None


def _build_basin_component_from_core_summary(
    basin_summary: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Build standalone basin component outputs from the already-flattened
    core report-card basin summary.

    Expected core summary columns include:
    - Source
    - MetricType
    - Scenario
    - Level
    - Region
    - Basin
    - FU
    - Constituent
    - Process
    - Units
    - Value
    """
    required = ["Scenario", "Level", "Region", "Basin", "Constituent", "Units", "Value"]
    missing = [c for c in required if c not in basin_summary.columns]
    if missing:
        raise KeyError(f"Core basin summary missing required columns: {missing}")

    basin_all = basin_summary.loc[basin_summary["Level"] == "Basin"].copy()

    basin_fu = basin_all.loc[basin_all["Source"] == "FU"].copy()
    basin_process = basin_all.loc[basin_all["Source"] == "PROCESS"].copy()

    basin_totals = (
        basin_all.groupby(
            ["Source", "MetricType", "Scenario", "Region", "Basin", "Constituent", "Units"],
            dropna=False,
            as_index=False,
        )["Value"]
        .sum()
    )

    fu_totals = (
        basin_fu.groupby(
            ["Scenario", "Region", "Basin", "Constituent", "Units"],
            dropna=False,
            as_index=False,
        )["Value"]
        .sum()
    )

    return {
        "basin_summary": basin_all,
        "basin_fu": basin_fu,
        "basin_process": basin_process,
        "basin_totals": basin_totals,
        "fu_totals": fu_totals,
    }


def run_basin_summary(
    cfg: GBRConfig,
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
    Export standalone basin component outputs.

    In bundle mode, this reuses the existing core basin summary CSV to avoid
    re-reading and re-merging large source output files.

    If no core basin summary CSV is found, it falls back to rebuilding basin
    scenario comparison outputs from source files.
    """
    out_dir = ensure_output_dir(output_dir)
    files: dict[str, Path] = {}

    core_basin_csv = _find_core_basin_summary_csv(bundle_dirs=bundle_dirs)

    if core_basin_csv is not None:
        basin_summary = pd.read_csv(core_basin_csv)
        result = _build_basin_component_from_core_summary(basin_summary)

        basin_summary_csv = out_dir / "basin_summary.csv"
        basin_fu_csv = out_dir / "basin_fu_summary.csv"
        basin_process_csv = out_dir / "basin_process_summary.csv"
        basin_totals_csv = out_dir / "basin_totals.csv"
        fu_totals_csv = out_dir / "basin_fu_totals.csv"

        result["basin_summary"].to_csv(basin_summary_csv, index=False)
        result["basin_fu"].to_csv(basin_fu_csv, index=False)
        result["basin_process"].to_csv(basin_process_csv, index=False)
        result["basin_totals"].to_csv(basin_totals_csv, index=False)
        result["fu_totals"].to_csv(fu_totals_csv, index=False)

        files["basin_output_csv"] = basin_summary_csv
        files["basin_fu_summary_csv"] = basin_fu_csv
        files["basin_process_summary_csv"] = basin_process_csv
        files["basin_totals_csv"] = basin_totals_csv
        files["basin_fu_totals_csv"] = fu_totals_csv

        workbook_path = out_dir / "basin_summary.xlsx"
        export_tables_to_excel(
            tables={
                "basin_summary": result["basin_summary"],
                "basin_fu": result["basin_fu"],
                "basin_process": result["basin_process"],
                "basin_totals": result["basin_totals"],
                "fu_totals": result["fu_totals"],
            },
            output_path=workbook_path,
            index=False,
        )
        files["basin_summary_workbook"] = workbook_path

        result["files"] = files
        result["source_file"] = core_basin_csv
        result["mode"] = "from_core_report_card_summary"

        return result

    reporting_units = "report_card" if units == "report" else "raw"

    rebuilt = build_basin_scenario_comparison(
        cfg=cfg,
        basin_scale=basin_scale,
        regions=regions if regions is not None else getattr(cfg, "regions", None),
        constituents=constituents,
        value_column=value_column,
        reporting_units=reporting_units,
    )

    basin_loads_csv = out_dir / "basin_fu_loads.csv"
    compare_ready_csv = out_dir / "basin_totals_compare_ready.csv"

    rebuilt["basin_loads"].to_csv(basin_loads_csv, index=False)
    rebuilt["compare_ready"].to_csv(compare_ready_csv, index=False)

    files["basin_output_csv"] = basin_loads_csv
    files["basin_compare_ready_csv"] = compare_ready_csv

    workbook_path = out_dir / "basin_summary.xlsx"
    export_tables_to_excel(
        tables={
            "basin_fu_loads": rebuilt["basin_loads"],
            "compare_ready": rebuilt["compare_ready"],
            "base_wide": rebuilt["base_wide"].reset_index(),
            "predev_wide": rebuilt["predev_wide"].reset_index(),
            "change_wide": rebuilt["change_wide"].reset_index(),
            "anthropogenic": rebuilt["anthropogenic"].reset_index(),
            "reduction": rebuilt["reduction"].reset_index(),
            "percent_reduction": rebuilt["percent_reduction"].reset_index(),
        },
        output_path=workbook_path,
        index=False,
    )
    files["basin_summary_workbook"] = workbook_path

    rebuilt["files"] = files
    rebuilt["mode"] = "rebuilt_from_source_outputs"

    return rebuilt