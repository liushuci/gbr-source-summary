"""
Final report-card style summary workflow for gbr_source_summary.

This module combines:
- FU scenario comparison outputs
- process summary outputs

into flat long-format tables for:
- GBR level
- Region level
- Basin level

It exports:
- one CSV for each level
- one combined CSV
- one Excel workbook containing all tables
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import GBRConfig
from .export import ensure_output_dir
from .export_excel import export_tables_to_excel
from .units import apply_units, label_for_units, rename_units_column
from .workflows_compare import (
    build_fu_basin_scenario_comparison,
    build_fu_scenario_comparison,
)
from .workflows_process import build_process_export_summaries


FU_SCENARIO_KEYS = {
    "predev": "PREDEV",
    "base": "BASE",
    "change": "CHANGE",
    "anthropogenic": "ANTHROPOGENIC",
    "reduction": "REDUCTION",
    "percent_reduction": "PERCENT_REDUCTION",
}

FU_REGION_SCENARIO_KEYS = {
    "predev_region": "PREDEV",
    "base_region": "BASE",
    "change_region": "CHANGE",
}

FU_BASIN_SCENARIO_KEYS = {
    "predev_basin": "PREDEV",
    "base_basin": "BASE",
    "change_basin": "CHANGE",
    "anthropogenic_basin": "ANTHROPOGENIC",
    "reduction_basin": "REDUCTION",
    "percent_reduction_basin": "PERCENT_REDUCTION",
}


SUMMARY_COLUMNS = [
    "Source",
    "MetricType",
    "Scenario",
    "Level",
    "Region",
    "Basin",
    "FU",
    "Constituent",
    "Process",
    "Units",
    "Value",
]


def _empty_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=SUMMARY_COLUMNS)


def _normalise_first_index_column(df: pd.DataFrame, name: str) -> pd.DataFrame:
    temp = df.copy().reset_index()

    if "index" in temp.columns:
        temp = temp.rename(columns={"index": name})
    elif temp.columns[0] != name:
        temp = temp.rename(columns={temp.columns[0]: name})

    return temp


def _flatten_fu_wide_table(
    df: pd.DataFrame,
    *,
    scenario: str,
    level: str,
    units: str,
    region: str | None = None,
    basin: str | None = None,
) -> pd.DataFrame:
    """
    Flatten one FU x constituent wide table to long format.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty_summary_df()

    temp = _normalise_first_index_column(df, "FU")

    value_vars = [c for c in temp.columns if c != "FU"]
    if not value_vars:
        return _empty_summary_df()

    temp = temp.melt(
        id_vars=["FU"],
        value_vars=value_vars,
        var_name="Constituent",
        value_name="Value",
    )

    temp["Source"] = "FU"
    temp["MetricType"] = "FU"
    temp["Scenario"] = scenario
    temp["Level"] = level
    temp["Region"] = region
    temp["Basin"] = basin
    temp["Process"] = pd.NA
    temp["Units"] = units

    return temp[SUMMARY_COLUMNS]


def _flatten_fu_gbr_tables(
    fu_result: dict[str, object],
    units: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for key, scenario_name in FU_SCENARIO_KEYS.items():
        df = fu_result.get(key)
        flat = _flatten_fu_wide_table(
            df,
            scenario=scenario_name,
            level="GBR",
            units=units,
        )
        if not flat.empty:
            frames.append(flat)

    if not frames:
        return _empty_summary_df()

    return pd.concat(frames, ignore_index=True)


def _flatten_fu_region_tables(
    fu_result: dict[str, object],
    units: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for key, scenario_name in FU_REGION_SCENARIO_KEYS.items():
        region_dict = fu_result.get(key, {})
        if not isinstance(region_dict, dict):
            continue

        for region, df in region_dict.items():
            flat = _flatten_fu_wide_table(
                df,
                scenario=scenario_name,
                level="Region",
                units=units,
                region=region,
            )
            if not flat.empty:
                frames.append(flat)

    if not frames:
        return _empty_summary_df()

    return pd.concat(frames, ignore_index=True)


def _flatten_fu_basin_tables(
    fu_basin_result: dict[str, object],
    units: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    for key, scenario_name in FU_BASIN_SCENARIO_KEYS.items():
        region_basin_dict = fu_basin_result.get(key, {})
        if not isinstance(region_basin_dict, dict):
            continue

        for region, basin_dict in region_basin_dict.items():
            if not isinstance(basin_dict, dict):
                continue

            for basin, df in basin_dict.items():
                flat = _flatten_fu_wide_table(
                    df,
                    scenario=scenario_name,
                    level="Basin",
                    units=units,
                    region=region,
                    basin=basin,
                )
                if not flat.empty:
                    frames.append(flat)

    if not frames:
        return _empty_summary_df()

    return pd.concat(frames, ignore_index=True)


def _convert_process_basin_tables(
    basin_by_region: dict[str, dict[str, dict[str, pd.DataFrame]]],
    *,
    cfg: GBRConfig,
    units: str,
) -> dict[str, dict[str, dict[str, pd.DataFrame]]]:
    """
    Convert raw basin-level process tables to requested units and relabel
    the single value column.

    build_process_export_summaries() converts region and combined process
    summaries, but not basin summaries.
    """
    out: dict[str, dict[str, dict[str, pd.DataFrame]]] = {}

    for region, basin_dict in basin_by_region.items():
        out[region] = {}

        for basin, constituent_dict in basin_dict.items():
            out[region][basin] = {}

            for constituent, df in constituent_dict.items():
                if df.empty:
                    out[region][basin][constituent] = df.copy()
                    continue

                df_units = apply_units(df, units=units, years=cfg.model_years)
                df_units = rename_units_column(
                    df_units,
                    base_name="LoadToRegExport",
                    units=units,
                )
                out[region][basin][constituent] = df_units

    return out


def _flatten_process_constituent_table(
    df: pd.DataFrame,
    *,
    constituent: str,
    scenario: str,
    level: str,
    units: str,
    region: str | None = None,
    basin: str | None = None,
) -> pd.DataFrame:
    """
    Flatten one process table (index=Process, one value column) to long format.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return _empty_summary_df()

    temp = _normalise_first_index_column(df, "Process")

    value_cols = [c for c in temp.columns if c != "Process"]
    if not value_cols:
        return _empty_summary_df()

    value_col = value_cols[0]
    temp = temp.rename(columns={value_col: "Value"})

    temp["Source"] = "PROCESS"
    temp["MetricType"] = "PROCESS"
    temp["Scenario"] = scenario
    temp["Level"] = level
    temp["Region"] = region
    temp["Basin"] = basin
    temp["FU"] = pd.NA
    temp["Constituent"] = constituent
    temp["Units"] = units

    return temp[SUMMARY_COLUMNS]


def _flatten_process_gbr_tables(
    process_result: dict[str, object],
    *,
    model: str,
    units: str,
) -> pd.DataFrame:
    combined = process_result.get("combined", {})
    frames: list[pd.DataFrame] = []

    if not isinstance(combined, dict):
        return _empty_summary_df()

    for constituent, df in combined.items():
        flat = _flatten_process_constituent_table(
            df,
            constituent=constituent,
            scenario=model.upper(),
            level="GBR",
            units=units,
        )
        if not flat.empty:
            frames.append(flat)

    if not frames:
        return _empty_summary_df()

    return pd.concat(frames, ignore_index=True)


def _flatten_process_region_tables(
    process_result: dict[str, object],
    *,
    model: str,
    units: str,
) -> pd.DataFrame:
    region_by_region = process_result.get("region_by_region", {})
    frames: list[pd.DataFrame] = []

    if not isinstance(region_by_region, dict):
        return _empty_summary_df()

    for region, constituent_dict in region_by_region.items():
        if not isinstance(constituent_dict, dict):
            continue

        for constituent, df in constituent_dict.items():
            flat = _flatten_process_constituent_table(
                df,
                constituent=constituent,
                scenario=model.upper(),
                level="Region",
                units=units,
                region=region,
            )
            if not flat.empty:
                frames.append(flat)

    if not frames:
        return _empty_summary_df()

    return pd.concat(frames, ignore_index=True)


def _flatten_process_basin_tables(
    basin_by_region: dict[str, dict[str, dict[str, pd.DataFrame]]],
    *,
    model: str,
    units: str,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    if not isinstance(basin_by_region, dict):
        return _empty_summary_df()

    for region, basin_dict in basin_by_region.items():
        if not isinstance(basin_dict, dict):
            continue

        for basin, constituent_dict in basin_dict.items():
            if not isinstance(constituent_dict, dict):
                continue

            for constituent, df in constituent_dict.items():
                flat = _flatten_process_constituent_table(
                    df,
                    constituent=constituent,
                    scenario=model.upper(),
                    level="Basin",
                    units=units,
                    region=region,
                    basin=basin,
                )
                if not flat.empty:
                    frames.append(flat)

    if not frames:
        return _empty_summary_df()

    return pd.concat(frames, ignore_index=True)


def _sort_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    sort_cols = [
        c
        for c in [
            "Source",
            "MetricType",
            "Scenario",
            "Level",
            "Region",
            "Basin",
            "Constituent",
            "FU",
            "Process",
        ]
        if c in df.columns
    ]
    return df.sort_values(sort_cols).reset_index(drop=True)


def _build_qa_summary_table(
    *,
    gbr_summary: pd.DataFrame,
    region_summary: pd.DataFrame,
    basin_summary: pd.DataFrame,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a compact QA summary table for the final report-card outputs.
    """
    qa_rows: list[dict[str, object]] = []

    def add_row(
        check_name: str,
        level: str,
        status: str,
        count: int,
        notes: str = "",
    ) -> None:
        qa_rows.append(
            {
                "Check": check_name,
                "Level": level,
                "Status": status,
                "Count": int(count),
                "Notes": notes,
            }
        )

    def check_missing_ids(
        df: pd.DataFrame,
        *,
        level: str,
        required_cols: list[str],
    ) -> None:
        if df.empty:
            add_row(
                "empty_output",
                level,
                "WARN",
                1,
                "Summary table is empty.",
            )
            return

        for col in required_cols:
            missing = int(df[col].isna().sum()) if col in df.columns else len(df)
            add_row(
                f"missing_{col}",
                level,
                "PASS" if missing == 0 else "WARN",
                missing,
                "" if missing == 0 else f"{missing} rows missing {col}.",
            )

    def check_duplicates(
        df: pd.DataFrame,
        *,
        level: str,
    ) -> None:
        if df.empty:
            add_row("duplicate_rows", level, "WARN", 0, "Summary table is empty.")
            return

        key_cols = ["Source", "MetricType", "Scenario", "Level", "Region", "Basin", "FU", "Constituent", "Process"]
        key_cols = [c for c in key_cols if c in df.columns]

        dup_count = int(df.duplicated(subset=key_cols, keep=False).sum())
        add_row(
            "duplicate_rows",
            level,
            "PASS" if dup_count == 0 else "WARN",
            dup_count,
            "" if dup_count == 0 else "Duplicate key rows found.",
        )

    def check_negative_values(df: pd.DataFrame, *, level: str) -> None:
        if df.empty or "Value" not in df.columns:
            add_row("negative_values", level, "WARN", 0, "No values available.")
            return

        neg_count = int((pd.to_numeric(df["Value"], errors="coerce") < 0).sum())
        add_row(
            "negative_values",
            level,
            "PASS" if neg_count == 0 else "WARN",
            neg_count,
            "Negative values may be valid for anthropogenic/reduction-type outputs."
            if neg_count > 0
            else "",
        )

    def check_percent_reduction_bounds(df: pd.DataFrame, *, level: str) -> None:
        if df.empty or "Scenario" not in df.columns or "Value" not in df.columns:
            add_row("percent_reduction_bounds", level, "WARN", 0, "No values available.")
            return

        pr = df.loc[df["Scenario"] == "PERCENT_REDUCTION"].copy()
        if pr.empty:
            add_row("percent_reduction_bounds", level, "WARN", 0, "No PERCENT_REDUCTION rows.")
            return

        vals = pd.to_numeric(pr["Value"], errors="coerce")
        bad = int(((vals < -100) | (vals > 100)).sum())
        add_row(
            "percent_reduction_bounds",
            level,
            "PASS" if bad == 0 else "WARN",
            bad,
            "" if bad == 0 else "Values outside [-100, 100].",
        )

    def check_missing_value(df: pd.DataFrame, *, level: str) -> None:
        if df.empty or "Value" not in df.columns:
            add_row("missing_value", level, "WARN", 0, "No values available.")
            return

        missing = int(pd.to_numeric(df["Value"], errors="coerce").isna().sum())
        add_row(
            "missing_value",
            level,
            "PASS" if missing == 0 else "WARN",
            missing,
            "" if missing == 0 else "Rows with missing numeric Value.",
        )

    # GBR checks
    check_missing_ids(
        gbr_summary,
        level="GBR",
        required_cols=["Source", "MetricType", "Scenario", "Level", "Constituent"],
    )
    check_duplicates(gbr_summary, level="GBR")
    check_negative_values(gbr_summary, level="GBR")
    check_percent_reduction_bounds(gbr_summary, level="GBR")
    check_missing_value(gbr_summary, level="GBR")

    # Region checks
    check_missing_ids(
        region_summary,
        level="Region",
        required_cols=["Source", "MetricType", "Scenario", "Level", "Region", "Constituent"],
    )
    check_duplicates(region_summary, level="Region")
    check_negative_values(region_summary, level="Region")
    check_percent_reduction_bounds(region_summary, level="Region")
    check_missing_value(region_summary, level="Region")

    # Basin checks
    check_missing_ids(
        basin_summary,
        level="Basin",
        required_cols=["Source", "MetricType", "Scenario", "Level", "Region", "Basin", "Constituent"],
    )
    check_duplicates(basin_summary, level="Basin")
    check_negative_values(basin_summary, level="Basin")
    check_percent_reduction_bounds(basin_summary, level="Basin")
    check_missing_value(basin_summary, level="Basin")

    # Whole summary
    if summary.empty:
        add_row("all_summary_empty", "ALL", "WARN", 1, "Final combined summary is empty.")
    else:
        add_row("all_summary_empty", "ALL", "PASS", 0, "")

    return pd.DataFrame(qa_rows)


def run_report_card_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    export_excel_workbook: bool = True,
) -> dict[str, object]:
    """
    Run the final report-card summary workflow.

    This:
    1. builds FU GBR/region/basin scenario summaries
    2. builds process GBR/region/basin summaries
    3. flattens them into long-format tables
    4. exports level-specific and combined outputs

    Returns
    -------
    dict[str, object]
        Dictionary containing:
        - fu_result
        - fu_basin_result
        - process_result
        - gbr_summary
        - region_summary
        - basin_summary
        - summary
        - files
    """
    out_dir = ensure_output_dir(output_dir)
    unit_label = label_for_units(units)

    fu_result = build_fu_scenario_comparison(
        cfg=cfg,
        regions=cfg.regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    fu_basin_result = build_fu_basin_scenario_comparison(
        cfg=cfg,
        regions=cfg.regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    basin_by_region, region_by_region, combined = build_process_export_summaries(
        cfg=cfg,
        model=process_model,
        regions=cfg.regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    process_result = {
        "basin_by_region": basin_by_region,
        "region_by_region": region_by_region,
        "combined": combined,
    }

    process_basin_converted = _convert_process_basin_tables(
        basin_by_region,
        cfg=cfg,
        units=units,
    )

    fu_gbr = _flatten_fu_gbr_tables(fu_result, units=units)
    fu_region = _flatten_fu_region_tables(fu_result, units=units)
    fu_basin = _flatten_fu_basin_tables(fu_basin_result, units=units)

    process_gbr = _flatten_process_gbr_tables(
        process_result,
        model=process_model,
        units=units,
    )
    process_region = _flatten_process_region_tables(
        process_result,
        model=process_model,
        units=units,
    )
    process_basin = _flatten_process_basin_tables(
        process_basin_converted,
        model=process_model,
        units=units,
    )

    gbr_summary = _sort_summary(
        pd.concat([fu_gbr, process_gbr], ignore_index=True)
        if not fu_gbr.empty or not process_gbr.empty
        else _empty_summary_df()
    )
    region_summary = _sort_summary(
        pd.concat([fu_region, process_region], ignore_index=True)
        if not fu_region.empty or not process_region.empty
        else _empty_summary_df()
    )
    basin_summary = _sort_summary(
        pd.concat([fu_basin, process_basin], ignore_index=True)
        if not fu_basin.empty or not process_basin.empty
        else _empty_summary_df()
    )

    summary = _sort_summary(
        pd.concat([gbr_summary, region_summary, basin_summary], ignore_index=True)
        if not gbr_summary.empty or not region_summary.empty or not basin_summary.empty
        else _empty_summary_df()
    )



    qa_summary = _build_qa_summary_table(
        gbr_summary=gbr_summary,
        region_summary=region_summary,
        basin_summary=basin_summary,
        summary=summary,
    )

    files: dict[str, Path] = {}




    gbr_csv = out_dir / f"report_card_summary_gbr_{unit_label}.csv"
    region_csv = out_dir / f"report_card_summary_region_{unit_label}.csv"
    basin_csv = out_dir / f"report_card_summary_basin_{unit_label}.csv"
    summary_csv = out_dir / f"report_card_summary_all_{unit_label}.csv"

    qa_csv = out_dir / f"report_card_qa_summary_{unit_label}.csv"



    gbr_summary.to_csv(gbr_csv, index=False)
    region_summary.to_csv(region_csv, index=False)
    basin_summary.to_csv(basin_csv, index=False)
    summary.to_csv(summary_csv, index=False)
    qa_summary.to_csv(qa_csv, index=False)

    files["gbr_summary_csv"] = gbr_csv
    files["region_summary_csv"] = region_csv
    files["basin_summary_csv"] = basin_csv
    files["summary_csv"] = summary_csv
    files["qa_summary_csv"] = qa_csv

    if export_excel_workbook:
        workbook_path = out_dir / f"report_card_summary_{unit_label}.xlsx"
        
        meta = pd.DataFrame({
            "Key": [
                "Generated",
                "Units",
                "Regions",
                "Process Model",
                "Constituents"
            ],
            "Value": [
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                units,
                ", ".join(cfg.regions),
                process_model,
                ", ".join(constituents) if constituents else "ALL"
            ]
        })
        
        
        export_tables_to_excel(
            tables={
                "metadata": meta, 
                "qa_summary": qa_summary,
                "all_summary": summary,
                "gbr_summary": gbr_summary,
                "region_summary": region_summary,
                "basin_summary": basin_summary,
                "fu_gbr": fu_gbr,
                "fu_region": fu_region,
                "fu_basin": fu_basin,
                "process_gbr": process_gbr,
                "process_region": process_region,
                "process_basin": process_basin,
            },
            output_path=workbook_path,
            index=False,
        )
        files["summary_workbook"] = workbook_path

    return {
        "fu_result": fu_result,
        "fu_basin_result": fu_basin_result,
        "process_result": process_result,
        "gbr_summary": gbr_summary,
        "region_summary": region_summary,
        "basin_summary": basin_summary,
        "summary": summary,
        "qa_summary": qa_summary,
        "files": files,
    }