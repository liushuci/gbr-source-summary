"""
Report-card summary and bundle wrapper for gbr_source_summary.

This module provides two layers:

1. Core report-card summary
   - FU scenario comparison outputs
   - process summary outputs
   - flattened long-format tables for GBR / Region / Basin
   - CSV + Excel + QA outputs

2. Bundle wrapper
   - creates a clean output folder structure
   - runs the core summary first
   - optionally runs extra workflow steps one by one
   - records step status and output files
   - writes a bundle README.txt

Notes
-----
- FU wide tables and process single-constituent tables cannot use
  apply_units(units="report") directly, because they do not contain a
  'Constituent' column. Those are converted manually here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any
import traceback

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

DEFAULT_BUNDLE_SUBDIRS = {
    "metadata": "00_metadata",
    "report_card_summary": "01_report_card_summary",
    "region_summary": "02_region_summary",
    "basin_summary": "03_basin_summary",
    "landuse_rainfall": "04_landuse_rainfall",
    "source_sink_summary": "05_source_sink_summary",
    "source_sink_sankey": "06_source_sink_sankey",
    "other": "90_other",
}

FILE_DESCRIPTIONS = {
    "metadata_csv": "Run metadata including config, regions, units, process model, and timestamp.",
    "qa_summary_csv": "QA checks for missing values, duplicates, negative values, and percent-reduction bounds.",
    "gbr_summary_csv": "GBR-level flattened report-card summary combining FU and process outputs.",
    "region_summary_csv": "Region-level flattened report-card summary combining FU and process outputs.",
    "basin_summary_csv": "Basin-level flattened report-card summary combining FU and process outputs.",
    "summary_csv": "Combined flattened summary across GBR, region, and basin levels.",
    "summary_workbook": "Excel workbook containing metadata, QA, and all core summary tables.",
    "bundle_metadata_csv": "Top-level metadata for the bundle run.",
    "bundle_step_summary_csv": "Step-by-step output index with one output file per row.",
    "bundle_readme_txt": "Human-readable overview of the bundle structure and outputs.",
    "region_output_csv": "Region summary outputs from an external workflow.",
    "basin_output_csv": "Basin summary outputs from an external workflow.",
    "landuse_rainfall_csv": "Land use and rainfall summary outputs.",
    "source_sink_summary_csv": "Source-sink summary outputs.",
    "sankey_plot": "Sankey diagram output.",
    "region_basin_totals_csv": "Basin totals used to roll up region scenario comparison outputs.",
    "region_basin_fu_loads_csv": "Underlying basin FU scenario loads used for region aggregation.",
    "region_summary_workbook": "Excel workbook containing region totals and scenario comparison tables.",
}


@dataclass
class StepResult:
    name: str
    status: str
    output_dir: Path
    files: dict[str, str]
    message: str = ""


def _empty_summary_df() -> pd.DataFrame:
    return pd.DataFrame(columns=SUMMARY_COLUMNS)


def _normalise_first_index_column(df: pd.DataFrame, name: str) -> pd.DataFrame:
    temp = df.copy().reset_index()

    if "index" in temp.columns:
        temp = temp.rename(columns={"index": name})
    elif temp.columns[0] != name:
        temp = temp.rename(columns={temp.columns[0]: name})

    return temp


def _report_unit_for_constituent(constituent: str | None) -> str:
    """
    Return the actual report-card unit for a constituent.
    """
    key = str(constituent).strip().upper() if constituent is not None else ""
    if key in {"FS", "CS"}:
        return "kt/yr"
    return "t/yr"


def _flatten_fu_wide_table(
    df: pd.DataFrame,
    *,
    scenario: str,
    level: str,
    units: str,
    region: str | None = None,
    basin: str | None = None,
) -> pd.DataFrame:
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

    if units == "report":
        temp["Units"] = temp["Constituent"].map(_report_unit_for_constituent)
    else:
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

    Process summary tables are single-constituent tables:
    - index = Process
    - one numeric value column
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

                df_units = df.copy()
                value_col = df_units.columns[0]
                df_units[value_col] = pd.to_numeric(
                    df_units[value_col], errors="coerce"
                ).fillna(0.0)

                if units == "report":
                    final_units = _report_unit_for_constituent(constituent)
                    if final_units == "kt/yr":
                        df_units[value_col] = df_units[value_col] / 1e6 / cfg.model_years
                    else:
                        df_units[value_col] = df_units[value_col] / 1e3 / cfg.model_years

                    df_units = rename_units_column(
                        df_units,
                        base_name="LoadToRegExport",
                        units=final_units,
                    )

                else:
                    df_units = apply_units(
                        df_units,
                        units=units,
                        years=cfg.model_years,
                    )
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

    if units == "report":
        temp["Units"] = _report_unit_for_constituent(constituent)
    else:
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
            add_row("empty_output", level, "WARN", 1, "Summary table is empty.")
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

        key_cols = [
            "Source",
            "MetricType",
            "Scenario",
            "Level",
            "Region",
            "Basin",
            "FU",
            "Constituent",
            "Process",
        ]
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

    check_missing_ids(
        gbr_summary,
        level="GBR",
        required_cols=["Source", "MetricType", "Scenario", "Level", "Constituent"],
    )
    check_duplicates(gbr_summary, level="GBR")
    check_negative_values(gbr_summary, level="GBR")
    check_percent_reduction_bounds(gbr_summary, level="GBR")
    check_missing_value(gbr_summary, level="GBR")

    check_missing_ids(
        region_summary,
        level="Region",
        required_cols=["Source", "MetricType", "Scenario", "Level", "Region", "Constituent"],
    )
    check_duplicates(region_summary, level="Region")
    check_negative_values(region_summary, level="Region")
    check_percent_reduction_bounds(region_summary, level="Region")
    check_missing_value(region_summary, level="Region")

    check_missing_ids(
        basin_summary,
        level="Basin",
        required_cols=["Source", "MetricType", "Scenario", "Level", "Region", "Basin", "Constituent"],
    )
    check_duplicates(basin_summary, level="Basin")
    check_negative_values(basin_summary, level="Basin")
    check_percent_reduction_bounds(basin_summary, level="Basin")
    check_missing_value(basin_summary, level="Basin")

    if summary.empty:
        add_row("all_summary_empty", "ALL", "WARN", 1, "Final combined summary is empty.")
    else:
        add_row("all_summary_empty", "ALL", "PASS", 0, "")

    return pd.DataFrame(qa_rows)


def _build_metadata_table(
    *,
    cfg: GBRConfig,
    constituents: list[str] | None,
    units: str,
    process_model: str,
    value_column: str,
    output_dir: Path,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Key": [
                "Generated",
                "OutputDir",
                "Units",
                "ProcessModel",
                "ValueColumn",
                "Regions",
                "Constituents",
                "ModelYears",
            ],
            "Value": [
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(output_dir),
                units,
                process_model,
                value_column,
                ", ".join(getattr(cfg, "regions", []) or []),
                ", ".join(constituents) if constituents else "ALL",
                getattr(cfg, "model_years", ""),
            ],
        }
    )


def _write_step_summary(step_results: list[StepResult], output_path: Path) -> pd.DataFrame:
    rows = []

    for s in step_results:
        if s.files:
            for file_key, file_path in s.files.items():
                rows.append(
                    {
                        "Step": s.name,
                        "Status": s.status,
                        "OutputDir": str(s.output_dir),
                        "FileType": file_key,
                        "FilePath": file_path,
                        "Description": FILE_DESCRIPTIONS.get(
                            file_key,
                            "No description available.",
                        ),
                        "Message": s.message,
                    }
                )
        else:
            rows.append(
                {
                    "Step": s.name,
                    "Status": s.status,
                    "OutputDir": str(s.output_dir),
                    "FileType": None,
                    "FilePath": None,
                    "Description": "No files produced.",
                    "Message": s.message,
                }
            )

    df = pd.DataFrame(rows)
    df = df.sort_values(["Step", "FileType"], na_position="last").reset_index(drop=True)
    df.to_csv(output_path, index=False)
    return df


def _write_bundle_readme(
    *,
    output_path: Path,
    output_root: Path,
    bundle_dirs: dict[str, Path],
    bundle_meta: pd.DataFrame,
    step_summary_df: pd.DataFrame,
) -> None:
    generated = ""
    units = ""
    process_model = ""
    regions = ""
    constituents = ""
    value_column = ""

    if not bundle_meta.empty and {"Key", "Value"}.issubset(bundle_meta.columns):
        meta_lookup = dict(zip(bundle_meta["Key"], bundle_meta["Value"]))
        generated = str(meta_lookup.get("Generated", ""))
        units = str(meta_lookup.get("Units", ""))
        process_model = str(meta_lookup.get("ProcessModel", ""))
        regions = str(meta_lookup.get("Regions", ""))
        constituents = str(meta_lookup.get("Constituents", ""))
        value_column = str(meta_lookup.get("ValueColumn", ""))

    lines: list[str] = []
    lines.append("GBR Source Summary - Report Card Bundle")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"Generated: {generated}")
    lines.append(f"Output root: {output_root}")
    lines.append(f"Units mode: {units}")
    lines.append(f"Process model: {process_model}")
    lines.append(f"Value column: {value_column}")
    lines.append(f"Regions: {regions}")
    lines.append(f"Constituents: {constituents}")
    lines.append("")
    lines.append("Bundle folders")
    lines.append("-" * 50)

    for key, path in bundle_dirs.items():
        lines.append(f"{key}: {path}")

    lines.append("")
    lines.append("Produced files")
    lines.append("-" * 50)

    if step_summary_df.empty:
        lines.append("No files were recorded.")
    else:
        for step_name in step_summary_df["Step"].dropna().astype(str).unique():
            step_rows = step_summary_df.loc[step_summary_df["Step"] == step_name].copy()
            if step_rows.empty:
                continue

            step_status = step_rows["Status"].iloc[0]
            step_message = step_rows["Message"].iloc[0]

            lines.append(f"[{step_name}]")
            lines.append(f"Status: {step_status}")
            if pd.notna(step_message) and str(step_message).strip():
                lines.append(f"Message: {step_message}")

            for _, row in step_rows.iterrows():
                file_type = row.get("FileType")
                file_path = row.get("FilePath")
                description = row.get("Description")

                if pd.isna(file_type) and pd.isna(file_path):
                    continue

                lines.append(f"  - {file_type}")
                lines.append(f"    Path: {file_path}")
                lines.append(f"    Description: {description}")

            lines.append("")

    lines.append("Notes")
    lines.append("-" * 50)
    lines.append("1. The step summary CSV contains one output file per row.")
    lines.append("2. Core report-card summary outputs are written to 01_report_card_summary.")
    lines.append("3. In flattened summary tables, Units shows actual units such as kt/yr or t/yr.")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


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
    Core FU + process report-card summary.
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

    meta = _build_metadata_table(
        cfg=cfg,
        constituents=constituents,
        units=units,
        process_model=process_model,
        value_column=value_column,
        output_dir=out_dir,
    )

    files: dict[str, Path] = {}

    metadata_csv = out_dir / "metadata.csv"
    qa_csv = out_dir / f"report_card_qa_summary_{unit_label}.csv"
    gbr_csv = out_dir / f"report_card_summary_gbr_{unit_label}.csv"
    region_csv = out_dir / f"report_card_summary_region_{unit_label}.csv"
    basin_csv = out_dir / f"report_card_summary_basin_{unit_label}.csv"
    summary_csv = out_dir / f"report_card_summary_all_{unit_label}.csv"

    meta.to_csv(metadata_csv, index=False)
    qa_summary.to_csv(qa_csv, index=False)
    gbr_summary.to_csv(gbr_csv, index=False)
    region_summary.to_csv(region_csv, index=False)
    basin_summary.to_csv(basin_csv, index=False)
    summary.to_csv(summary_csv, index=False)

    files["metadata_csv"] = metadata_csv
    files["qa_summary_csv"] = qa_csv
    files["gbr_summary_csv"] = gbr_csv
    files["region_summary_csv"] = region_csv
    files["basin_summary_csv"] = basin_csv
    files["summary_csv"] = summary_csv

    if export_excel_workbook:
        workbook_path = out_dir / f"report_card_summary_{unit_label}.xlsx"
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
        "metadata": meta,
        "files": files,
    }


def run_fu_process_report_card_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    export_excel_workbook: bool = True,
) -> dict[str, object]:
    return run_report_card_summary(
        cfg=cfg,
        output_dir=output_dir,
        constituents=constituents,
        value_column=value_column,
        units=units,
        process_model=process_model,
        export_excel_workbook=export_excel_workbook,
    )


def run_report_card_bundle(
    cfg: GBRConfig,
    output_root: str | Path,
    *,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    export_excel_workbook: bool = True,
    extra_steps: dict[str, Callable[..., Any]] | None = None,
    fail_fast: bool = False,
) -> dict[str, object]:
    root = ensure_output_dir(output_root)

    bundle_dirs: dict[str, Path] = {
        key: ensure_output_dir(root / subdir)
        for key, subdir in DEFAULT_BUNDLE_SUBDIRS.items()
    }

    step_results: list[StepResult] = []
    outputs: dict[str, object] = {}

    bundle_meta = _build_metadata_table(
        cfg=cfg,
        constituents=constituents,
        units=units,
        process_model=process_model,
        value_column=value_column,
        output_dir=root,
    )
    bundle_meta_path = bundle_dirs["metadata"] / "bundle_metadata.csv"
    bundle_meta.to_csv(bundle_meta_path, index=False)

    try:
        core = run_report_card_summary(
            cfg=cfg,
            output_dir=bundle_dirs["report_card_summary"],
            constituents=constituents,
            value_column=value_column,
            units=units,
            process_model=process_model,
            export_excel_workbook=export_excel_workbook,
        )
        outputs["report_card_summary"] = core
        step_results.append(
            StepResult(
                name="report_card_summary",
                status="SUCCESS",
                output_dir=bundle_dirs["report_card_summary"],
                files={k: str(v) for k, v in core.get("files", {}).items()},
                message="Core FU + process report-card summary completed.",
            )
        )
    except Exception as exc:
        step_results.append(
            StepResult(
                name="report_card_summary",
                status="FAILED",
                output_dir=bundle_dirs["report_card_summary"],
                files={},
                message=f"{exc}\n\n{traceback.format_exc()}",
            )
        )
        if fail_fast:
            step_summary_path = bundle_dirs["metadata"] / "bundle_step_summary.csv"
            step_summary_df = _write_step_summary(step_results, step_summary_path)

            readme_path = bundle_dirs["metadata"] / "README.txt"
            _write_bundle_readme(
                output_path=readme_path,
                output_root=root,
                bundle_dirs=bundle_dirs,
                bundle_meta=bundle_meta,
                step_summary_df=step_summary_df,
            )
            raise

    for step_name, step_fn in (extra_steps or {}).items():
        step_dir = bundle_dirs.get(step_name, ensure_output_dir(bundle_dirs["other"] / step_name))

        try:
            result = step_fn(
                cfg=cfg,
                output_dir=step_dir,
                constituents=constituents,
                value_column=value_column,
                units=units,
                process_model=process_model,
                bundle_dirs=bundle_dirs,
            )

            files = {}
            if isinstance(result, dict):
                raw_files = result.get("files", {})
                if isinstance(raw_files, dict):
                    files = {k: str(v) for k, v in raw_files.items()}

            outputs[step_name] = result
            step_results.append(
                StepResult(
                    name=step_name,
                    status="SUCCESS",
                    output_dir=step_dir,
                    files=files,
                    message="Completed.",
                )
            )

        except NotImplementedError as exc:
            step_results.append(
                StepResult(
                    name=step_name,
                    status="SKIPPED",
                    output_dir=step_dir,
                    files={},
                    message=str(exc),
                )
            )
            if fail_fast:
                step_summary_path = bundle_dirs["metadata"] / "bundle_step_summary.csv"
                step_summary_df = _write_step_summary(step_results, step_summary_path)

                readme_path = bundle_dirs["metadata"] / "README.txt"
                _write_bundle_readme(
                    output_path=readme_path,
                    output_root=root,
                    bundle_dirs=bundle_dirs,
                    bundle_meta=bundle_meta,
                    step_summary_df=step_summary_df,
                )
                raise

        except Exception as exc:
            step_results.append(
                StepResult(
                    name=step_name,
                    status="FAILED",
                    output_dir=step_dir,
                    files={},
                    message=f"{exc}\n\n{traceback.format_exc()}",
                )
            )
            if fail_fast:
                step_summary_path = bundle_dirs["metadata"] / "bundle_step_summary.csv"
                step_summary_df = _write_step_summary(step_results, step_summary_path)

                readme_path = bundle_dirs["metadata"] / "README.txt"
                _write_bundle_readme(
                    output_path=readme_path,
                    output_root=root,
                    bundle_dirs=bundle_dirs,
                    bundle_meta=bundle_meta,
                    step_summary_df=step_summary_df,
                )
                raise

    step_summary_path = bundle_dirs["metadata"] / "bundle_step_summary.csv"
    step_summary_df = _write_step_summary(step_results, step_summary_path)

    readme_path = bundle_dirs["metadata"] / "README.txt"
    _write_bundle_readme(
        output_path=readme_path,
        output_root=root,
        bundle_dirs=bundle_dirs,
        bundle_meta=bundle_meta,
        step_summary_df=step_summary_df,
    )

    return {
        "output_root": root,
        "bundle_dirs": bundle_dirs,
        "bundle_metadata": bundle_meta,
        "step_summary": step_summary_df,
        "steps": step_results,
        "outputs": outputs,
        "files": {
            "bundle_metadata_csv": bundle_meta_path,
            "bundle_step_summary_csv": step_summary_path,
            "bundle_readme_txt": readme_path,
        },
    }