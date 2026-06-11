from __future__ import annotations

import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import GBRConfig
from .export import ensure_output_dir
from .export_excel import export_tables_to_excel
from .naming import (
    standardise_constituent_names,
    standardise_management_unit_names,
)
from .units import apply_units
from .package_data import package_data_path


SOURCE_SINK_CONSTITUENTS = ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

REQUIRED_BUDGET_ELEMENTS = [
    "Hillslope",
    "Gully",
    "Undefined",
    "Diffuse Dissolved",
    "Seepage",
    "Leached",
    "TimeSeries Contributed Seepage",
    "Extraction",
    "Node Loss",
    "Residual Node Storage",
    "DWC Contributed Seepage",
    "Link Yield",
    "Link In Flow",
    "Residual Link Storage",
    "Link Initial Load",
    "Streambank",
    "Channel Remobilisation",
    "Stream Deposition",
    "Reservoir Decay",
    "Reservoir Deposition",
    "Flood Plain Deposition",
    "Point Source",
    "Stream Decay",
]

SEDIMENT_PARTICULATE_CONSTITUENTS = {"FS", "CS", "PN", "PP"}
DISSOLVED_CONSTITUENTS = {"DIN", "DON", "DIP", "DOP"}

DEFAULT_VALUE_COLUMN = "Total_Load_in_Kg"
DEFAULT_EXPORT_VALUE_COLUMN = "LoadToRegExport (kg)"

LOSS_BUDGET_GROUPS = {
    "Extraction + Other Minor Losses",
    "FloodPlainDeposition",
    "ReservoirDeposition",
    "StreamDeposition",
}

SUPPLY_BUDGET_GROUPS = {
    "Hillslope",
    "Streambank",
    "Gully",
    "ChannelRemobilisation",
    "SurfaceRunoff",
    "Seepage",
    "PointSource",
}

EXPORT_BUDGET_GROUPS = {
    "HillslopeExport",
    "StreambankExport",
    "GullyExport",
    "ChannelRemobilisationExport",
    "SurfaceRunoffExport",
    "SeepageExport",
    "PointSourceExport",
}


# =============================================================================
# Basic helpers
# =============================================================================


def _ensure_required_budget_elements(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    return out.reindex(REQUIRED_BUDGET_ELEMENTS, fill_value=0.0)


def _normalise_budget_element_names(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse hillslope budget variants used in RawResults.csv."""
    out = df.copy()
    if "BudgetElement" in out.columns:
        hillslope_variants = {
            "Hillslope surface soil",
            "Hillslope sub-surface soil",
            "Hillslope no source distinction",
        }
        out.loc[out["BudgetElement"].isin(hillslope_variants), "BudgetElement"] = "Hillslope"
    return out


def _standardise_source_sink_names(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Constituent" in out.columns:
        out["Constituent"] = standardise_constituent_names(out["Constituent"])
    if "Basin" in out.columns:
        out["Basin"] = standardise_management_unit_names(out["Basin"])
    return out


def _apply_source_sink_report_units(
    df: pd.DataFrame,
    model_years: float,
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    required = ["Constituent", value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns for source-sink unit conversion: {missing}")

    temp_value_col = "LoadToRegExport (kg)"
    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)
    out = out.rename(columns={value_column: temp_value_col})

    out = apply_units(
        out,
        units="report",
        years=int(model_years),
        value_column=temp_value_col,
    )

    out = out.rename(columns={temp_value_col: value_column})

    # apply_units usually converts FS to kt/yr and nutrients to t/yr.
    # CS should be reported with FS in kt/yr.
    cs_mask = out["Constituent"] == "CS"
    if cs_mask.any():
        out.loc[cs_mask, "Units"] = "kt/yr"
        out.loc[cs_mask, value_column] = pd.to_numeric(
            out.loc[cs_mask, value_column],
            errors="coerce",
        ) / 1000.0

    return out


# =============================================================================
# Budget source/sink summary from RawResults.csv
# =============================================================================


def summarise_basin_budget_for_constituent(
    df_basin_constituent: pd.DataFrame,
    constituent: str,
    region: str,
) -> pd.DataFrame:
    if df_basin_constituent.empty:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    work = (
        df_basin_constituent.groupby("BudgetElement", dropna=False, as_index=True)[DEFAULT_VALUE_COLUMN]
        .sum()
        .to_frame()
    )
    work[DEFAULT_VALUE_COLUMN] = pd.to_numeric(work[DEFAULT_VALUE_COLUMN], errors="coerce").fillna(0.0)
    work = _ensure_required_budget_elements(work)

    def val(name: str) -> float:
        return float(work.loc[name, DEFAULT_VALUE_COLUMN]) if name in work.index else 0.0

    rows: list[dict[str, object]] = []

    if constituent in SEDIMENT_PARTICULATE_CONSTITUENTS:
        hillslope = val("Hillslope")
        undefined = val("Undefined")

        # Preserve existing region-specific FS handling.
        if constituent == "FS":
            if region not in {"CY", "BU", "FI", "BM"}:
                hillslope += undefined
        else:
            hillslope += undefined

        rows = [
            {"BudgetGroup": "Hillslope", DEFAULT_VALUE_COLUMN: hillslope},
            {"BudgetGroup": "Streambank", DEFAULT_VALUE_COLUMN: val("Streambank")},
            {"BudgetGroup": "Gully", DEFAULT_VALUE_COLUMN: val("Gully")},
            {"BudgetGroup": "ChannelRemobilisation", DEFAULT_VALUE_COLUMN: val("Channel Remobilisation")},
            {
                "BudgetGroup": "Extraction + Other Minor Losses",
                DEFAULT_VALUE_COLUMN: (
                    val("Extraction")
                    + val("Node Loss")
                    + val("Residual Link Storage")
                    + val("Residual Node Storage")
                ),
            },
            {"BudgetGroup": "FloodPlainDeposition", DEFAULT_VALUE_COLUMN: val("Flood Plain Deposition")},
            {"BudgetGroup": "ReservoirDeposition", DEFAULT_VALUE_COLUMN: val("Reservoir Deposition")},
            {"BudgetGroup": "StreamDeposition", DEFAULT_VALUE_COLUMN: val("Stream Deposition")},
        ]

    elif constituent in DISSOLVED_CONSTITUENTS:
        if constituent == "DIN":
            if region in {"CY", "BU", "BM"}:
                surface_runoff = val("Diffuse Dissolved") + val("Hillslope")
            elif region == "FI":
                surface_runoff = val("Diffuse Dissolved")
            else:
                surface_runoff = val("Undefined") + val("Diffuse Dissolved") + val("Hillslope")
        else:
            surface_runoff = val("Undefined") + val("Diffuse Dissolved") + val("Hillslope")

        rows = [
            {"BudgetGroup": "SurfaceRunoff", DEFAULT_VALUE_COLUMN: surface_runoff},
            {"BudgetGroup": "Seepage", DEFAULT_VALUE_COLUMN: val("Seepage")},
            {"BudgetGroup": "PointSource", DEFAULT_VALUE_COLUMN: val("Point Source")},
            {
                "BudgetGroup": "Extraction + Other Minor Losses",
                DEFAULT_VALUE_COLUMN: (
                    val("Extraction")
                    + val("Node Loss")
                    + val("Residual Link Storage")
                    + val("Residual Node Storage")
                ),
            },
        ]
    else:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    out = pd.DataFrame(rows)
    out["Constituent"] = constituent
    return out


# =============================================================================
# Process export summary from RegContributorDataGrid.csv
# =============================================================================


def summarise_export_for_constituent(
    df_export_constituent: pd.DataFrame,
    constituent: str,
    value_column: str = DEFAULT_EXPORT_VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Convert process export rows into export groups used by Sankey.

    This must use RegContributorDataGrid / contributor output, not RawResults.csv.
    """
    if df_export_constituent.empty:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    work = (
        df_export_constituent.groupby("Process", dropna=False, as_index=True)[value_column]
        .sum()
        .to_frame()
    )
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce").fillna(0.0)

    def val(name: str) -> float:
        return float(work.loc[name, value_column]) if name in work.index else 0.0

    if constituent in SEDIMENT_PARTICULATE_CONSTITUENTS:
        hillslope_export = (
            val("Hillslope")
            + val("Hillslope surface soil")
            + val("Hillslope sub-surface soil")
            + val("Hillslope no source distinction")
            + val("Undefined")
        )
        rows = [
            {"BudgetGroup": "HillslopeExport", DEFAULT_VALUE_COLUMN: hillslope_export},
            {"BudgetGroup": "StreambankExport", DEFAULT_VALUE_COLUMN: val("Streambank")},
            {"BudgetGroup": "GullyExport", DEFAULT_VALUE_COLUMN: val("Gully")},
            {"BudgetGroup": "ChannelRemobilisationExport", DEFAULT_VALUE_COLUMN: val("Channel Remobilisation")},
        ]

    elif constituent in DISSOLVED_CONSTITUENTS:
        surface_runoff_export = (
            val("Undefined")
            + val("Diffuse Dissolved")
            + val("Hillslope")
            + val("Hillslope surface soil")
            + val("Hillslope sub-surface soil")
            + val("Hillslope no source distinction")
        )
        rows = [
            {"BudgetGroup": "SurfaceRunoffExport", DEFAULT_VALUE_COLUMN: surface_runoff_export},
            {"BudgetGroup": "SeepageExport", DEFAULT_VALUE_COLUMN: val("Seepage")},
            {"BudgetGroup": "PointSourceExport", DEFAULT_VALUE_COLUMN: val("Point Source")},
        ]
    else:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    out = pd.DataFrame(rows)
    out["Constituent"] = constituent
    return out


# =============================================================================
# Generic grouped builders
# =============================================================================


def _build_source_sink_summary_from_grouped_raw(
    raw_results: pd.DataFrame,
    *,
    region: str,
    scenario: str,
    group_column: str,
    group_name: str,
    constituent_column: str = "Constituent",
    budget_element_column: str = "BudgetElement",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    required = [group_column, constituent_column, budget_element_column, value_column]
    missing = [c for c in required if c not in raw_results.columns]
    if missing:
        raise KeyError(f"Missing required columns in raw_results: {missing}")

    work = raw_results.rename(
        columns={
            group_column: group_name,
            constituent_column: "Constituent",
            budget_element_column: "BudgetElement",
            value_column: DEFAULT_VALUE_COLUMN,
        }
    ).copy()

    work = _normalise_budget_element_names(work)
    work["Constituent"] = standardise_constituent_names(work["Constituent"])
    work[DEFAULT_VALUE_COLUMN] = pd.to_numeric(work[DEFAULT_VALUE_COLUMN], errors="coerce").fillna(0.0)
    work = work.loc[work[group_name].notna()].copy()
    work[group_name] = work[group_name].astype(str).str.strip()
    work = work.loc[work["Constituent"].isin(SOURCE_SINK_CONSTITUENTS)].copy()

    rows: list[pd.DataFrame] = []
    for (group_value, constituent), df_gc in work.groupby([group_name, "Constituent"], dropna=False):
        summary = summarise_basin_budget_for_constituent(
            df_basin_constituent=df_gc[["BudgetElement", DEFAULT_VALUE_COLUMN]].copy(),
            constituent=str(constituent),
            region=region,
        )
        if summary.empty:
            continue
        summary["Region"] = region
        summary["Scenario"] = scenario
        summary[group_name] = group_value
        summary["Units"] = "kg"
        rows.append(summary)

    cols = ["Region", "Scenario", group_name, "Constituent", "BudgetGroup", DEFAULT_VALUE_COLUMN, "Units"]
    if not rows:
        return pd.DataFrame(columns=cols)

    out = pd.concat(rows, ignore_index=True)[cols]
    if group_name == "Basin":
        out = _standardise_source_sink_names(out)
    return out


def _build_export_summary_from_grouped_contributor(
    export_results: pd.DataFrame,
    *,
    region: str,
    scenario: str,
    group_column: str,
    group_name: str,
    constituent_column: str = "Constituent",
    process_column: str = "Process",
    value_column: str = DEFAULT_EXPORT_VALUE_COLUMN,
) -> pd.DataFrame:
    required = [group_column, constituent_column, process_column, value_column]
    missing = [c for c in required if c not in export_results.columns]
    if missing:
        raise KeyError(f"Missing required columns in export_results: {missing}")

    work = export_results.rename(
        columns={
            group_column: group_name,
            constituent_column: "Constituent",
            process_column: "Process",
            value_column: DEFAULT_VALUE_COLUMN,
        }
    ).copy()

    work["Constituent"] = standardise_constituent_names(work["Constituent"])
    work[DEFAULT_VALUE_COLUMN] = pd.to_numeric(work[DEFAULT_VALUE_COLUMN], errors="coerce").fillna(0.0)
    work = work.loc[work[group_name].notna()].copy()
    work[group_name] = work[group_name].astype(str).str.strip()
    work = work.loc[work["Constituent"].isin(SOURCE_SINK_CONSTITUENTS)].copy()

    rows: list[pd.DataFrame] = []
    for (group_value, constituent), df_gc in work.groupby([group_name, "Constituent"], dropna=False):
        summary = summarise_export_for_constituent(
            df_export_constituent=df_gc[["Process", DEFAULT_VALUE_COLUMN]].copy(),
            constituent=str(constituent),
            value_column=DEFAULT_VALUE_COLUMN,
        )
        if summary.empty:
            continue
        summary["Region"] = region
        summary["Scenario"] = scenario
        summary[group_name] = group_value
        summary["Units"] = "kg"
        rows.append(summary)

    cols = ["Region", "Scenario", group_name, "Constituent", "BudgetGroup", DEFAULT_VALUE_COLUMN, "Units"]
    if not rows:
        return pd.DataFrame(columns=cols)

    out = pd.concat(rows, ignore_index=True)[cols]
    if group_name == "Basin":
        out = _standardise_source_sink_names(out)
    return out


def build_subcat_source_sink_summary_from_raw(
    raw_results: pd.DataFrame,
    region: str,
    scenario: str,
    subcat_column: str = "ModelElement",
    constituent_column: str = "Constituent",
    budget_element_column: str = "BudgetElement",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    return _build_source_sink_summary_from_grouped_raw(
        raw_results=raw_results,
        region=region,
        scenario=scenario,
        group_column=subcat_column,
        group_name="Subcatchment",
        constituent_column=constituent_column,
        budget_element_column=budget_element_column,
        value_column=value_column,
    )


def build_basin_source_sink_summary_from_raw(
    raw_results: pd.DataFrame,
    region: str,
    scenario: str,
    basin_column: str = "Manag_Unit_48",
    constituent_column: str = "Constituent",
    budget_element_column: str = "BudgetElement",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    return _build_source_sink_summary_from_grouped_raw(
        raw_results=raw_results,
        region=region,
        scenario=scenario,
        group_column=basin_column,
        group_name="Basin",
        constituent_column=constituent_column,
        budget_element_column=budget_element_column,
        value_column=value_column,
    )


def build_subcat_export_summary_from_contributor(
    export_results: pd.DataFrame,
    region: str,
    scenario: str,
    subcat_column: str = "ModelElement",
    constituent_column: str = "Constituent",
    process_column: str = "Process",
    value_column: str = DEFAULT_EXPORT_VALUE_COLUMN,
) -> pd.DataFrame:
    return _build_export_summary_from_grouped_contributor(
        export_results=export_results,
        region=region,
        scenario=scenario,
        group_column=subcat_column,
        group_name="Subcatchment",
        constituent_column=constituent_column,
        process_column=process_column,
        value_column=value_column,
    )


def build_basin_export_summary_from_contributor(
    export_results: pd.DataFrame,
    region: str,
    scenario: str,
    basin_column: str = "Manag_Unit_48",
    constituent_column: str = "Constituent",
    process_column: str = "Process",
    value_column: str = DEFAULT_EXPORT_VALUE_COLUMN,
) -> pd.DataFrame:
    return _build_export_summary_from_grouped_contributor(
        export_results=export_results,
        region=region,
        scenario=scenario,
        group_column=basin_column,
        group_name="Basin",
        constituent_column=constituent_column,
        process_column=process_column,
        value_column=value_column,
    )


# =============================================================================
# Combining and QA
# =============================================================================


def append_export_groups(
    source_sink_df: pd.DataFrame,
    export_df: pd.DataFrame,
    *,
    spatial_cols: list[str],
    constituent_col: str = "Constituent",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    if source_sink_df.empty:
        return source_sink_df.copy()

    required_ss = spatial_cols + [constituent_col, "BudgetGroup", value_column]
    missing_ss = [c for c in required_ss if c not in source_sink_df.columns]
    if missing_ss:
        raise KeyError(f"Missing required columns in source_sink_df: {missing_ss}")

    required_exp = spatial_cols + [constituent_col, "BudgetGroup", value_column]
    missing_exp = [c for c in required_exp if c not in export_df.columns]
    if missing_exp:
        raise KeyError(f"Missing required columns in export_df: {missing_exp}")

    exp = export_df.copy()
    exp[value_column] = pd.to_numeric(exp[value_column], errors="coerce").fillna(0.0)
    exp = exp.loc[exp["BudgetGroup"].isin(EXPORT_BUDGET_GROUPS)].copy()
    if exp.empty:
        return source_sink_df.copy()

    out = source_sink_df.copy()
    if "Units" not in exp.columns:
        exp["Units"] = out["Units"].dropna().iloc[0] if "Units" in out.columns and not out["Units"].dropna().empty else "kg"

    common_cols = [c for c in out.columns if c in exp.columns]
    combined = pd.concat([out, exp[common_cols].copy()], ignore_index=True)
    dedupe_cols = [c for c in combined.columns if c != value_column]
    combined = combined.groupby(dedupe_cols, dropna=False, as_index=False)[value_column].sum()
    return combined


def build_region_source_sink_summary(
    basin_source_sink: pd.DataFrame,
    scenario: str = "BASE",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    required = ["Region", "Scenario", "Constituent", "BudgetGroup", "Units", value_column]
    missing = [c for c in required if c not in basin_source_sink.columns]
    if missing:
        raise KeyError(f"Missing required columns in basin_source_sink: {missing}")

    work = basin_source_sink.loc[basin_source_sink["Scenario"] == scenario].copy()
    return (
        work.groupby(["Region", "Scenario", "Constituent", "BudgetGroup", "Units"], dropna=False, as_index=False)[value_column]
        .sum()
    )


def build_gbr_source_sink_summary(
    region_source_sink: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    required = ["Scenario", "Constituent", "BudgetGroup", "Units", value_column]
    missing = [c for c in required if c not in region_source_sink.columns]
    if missing:
        raise KeyError(f"Missing required columns in region_source_sink: {missing}")

    return (
        region_source_sink.groupby(["Scenario", "Constituent", "BudgetGroup", "Units"], dropna=False, as_index=False)[value_column]
        .sum()
    )


def convert_source_sink_to_annual_units(
    df: pd.DataFrame,
    model_years: float,
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    return _apply_source_sink_report_units(df=df, model_years=model_years, value_column=value_column)


def add_display_value(
    df: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
    group_column: str = "BudgetGroup",
) -> pd.DataFrame:
    required = [group_column, value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns for add_display_value: {missing}")

    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)
    out["DisplayValue"] = out[value_column]

    neg_mask = out[group_column].isin(LOSS_BUDGET_GROUPS | EXPORT_BUDGET_GROUPS)
    out.loc[neg_mask, "DisplayValue"] = -out.loc[neg_mask, value_column].abs()

    pos_mask = out[group_column].isin(SUPPLY_BUDGET_GROUPS)
    out.loc[pos_mask, "DisplayValue"] = out.loc[pos_mask, value_column].abs()

    known_mask = out[group_column].isin(SUPPLY_BUDGET_GROUPS | LOSS_BUDGET_GROUPS | EXPORT_BUDGET_GROUPS)
    out.loc[~known_mask, "DisplayValue"] = out.loc[~known_mask, value_column]
    return out


def build_sankey_links_from_summary(
    df: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
    group_column: str = "BudgetGroup",
    central_node: str = "Export",
) -> pd.DataFrame:
    required = [group_column, value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns for build_sankey_links_from_summary: {missing}")

    work = df.copy()
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce").fillna(0.0)
    links: list[dict[str, object]] = []

    for _, row in work.iterrows():
        group = row[group_column]
        value = abs(float(row[value_column]))
        if value == 0:
            continue
        if group in LOSS_BUDGET_GROUPS or group in EXPORT_BUDGET_GROUPS:
            links.append({"source": central_node, "target": group, "value": value, "BudgetGroup": group})
        else:
            links.append({"source": group, "target": central_node, "value": value, "BudgetGroup": group})
    return pd.DataFrame(links)


def check_source_sink_balance(
    df: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
    group_column: str = "BudgetGroup",
) -> float:
    work = add_display_value(df=df, value_column=value_column, group_column=group_column)
    return float(work["DisplayValue"].sum())


# =============================================================================
# Read/join helpers
# =============================================================================


def read_raw_results_table(raw_results_path: str | Path) -> pd.DataFrame:
    return pd.read_csv(raw_results_path)


def read_region_lookup_table(lookup_path: str | Path) -> pd.DataFrame:
    return pd.read_csv(lookup_path)


def join_raw_results_to_basin_lookup(
    raw_results: pd.DataFrame,
    lookup_table: pd.DataFrame,
    raw_model_element_col: str = "ModelElement",
    lookup_model_element_col: str | None = None,
) -> pd.DataFrame:
    if raw_model_element_col not in raw_results.columns:
        raise KeyError(
            f"Missing raw model element column: {raw_model_element_col}. "
            f"Raw columns: {list(raw_results.columns)}"
        )

    lut = lookup_table.copy()
    if lookup_model_element_col is None:
        for c in ["ModelElement", "Reg_SC", "SUBCAT", "Subcat", "Subcatchment", "Model_Element"]:
            if c in lut.columns:
                lookup_model_element_col = c
                break

    if lookup_model_element_col is None or lookup_model_element_col not in lut.columns:
        raise KeyError(f"Could not find lookup model element column. LUT columns: {list(lut.columns)}")

    raw = raw_results.copy()
    raw["_join_model_element"] = raw[raw_model_element_col].astype(str).str.strip()
    lut["_join_model_element"] = lut[lookup_model_element_col].astype(str).str.strip()

    out = pd.merge(raw, lut, on="_join_model_element", how="left", suffixes=("", "_lut"))
    return out.drop(columns=["_join_model_element"])


def build_basin_source_sink_for_region_scenarios(
    region: str,
    scenarios: Iterable[str],
    raw_results_by_scenario: dict[str, pd.DataFrame],
    basin_lookup: pd.DataFrame,
    basin_column: str = "Manag_Unit_48",
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for scenario in scenarios:
        if scenario not in raw_results_by_scenario:
            raise KeyError(f"Missing raw results for scenario: {scenario}")
        joined = join_raw_results_to_basin_lookup(
            raw_results=raw_results_by_scenario[scenario],
            lookup_table=basin_lookup,
        )
        rows.append(
            build_basin_source_sink_summary_from_raw(
                raw_results=joined,
                region=region,
                scenario=scenario,
                basin_column=basin_column,
                constituent_column="Constituent",
                budget_element_column="BudgetElement",
                value_column=DEFAULT_VALUE_COLUMN,
            )
        )

    if not rows:
        return pd.DataFrame(columns=["Region", "Scenario", "Basin", "Constituent", "BudgetGroup", DEFAULT_VALUE_COLUMN, "Units"])
    return pd.concat(rows, ignore_index=True)


# =============================================================================
# Wrapper-ready runners
# =============================================================================


@lru_cache(maxsize=None)
def _read_csv_cached(path_str: str) -> pd.DataFrame:
    return pd.read_csv(path_str, low_memory=False, on_bad_lines="skip")


def _read_csv(path: str | Path) -> pd.DataFrame:
    return _read_csv_cached(str(path))


def _cfg_rc_label(cfg: GBRConfig) -> str:
    for attr in ["rc", "RC", "run_name", "scenario_label"]:
        value = getattr(cfg, attr, None)
        if value:
            return str(value)
    return "Gold_93_23"


def _cfg_main_path(cfg: GBRConfig) -> Path:
    main_path = getattr(cfg, "main_path", None)
    if main_path is None:
        raise AttributeError("cfg.main_path is required for source-sink summary.")
    return Path(main_path)


def _scenario_folders(cfg: GBRConfig, region: str, scenario: str) -> list[Path]:
    scenario = str(scenario).upper()
    rc_label = _cfg_rc_label(cfg)
    main_path = _cfg_main_path(cfg)
    return [
        main_path / "Gold_ResultsSets_PointOfTruth" / region / "Model_Outputs" / f"{scenario}_{rc_label}",
        main_path / region / "Model_Outputs" / f"{scenario}_{rc_label}",
        main_path / "Model_Outputs" / region / f"{scenario}_{rc_label}",
    ]


def _find_raw_results_path(
    cfg: GBRConfig,
    region: str,
    scenario: str,
) -> Path:
    """Find RawResults.csv using automatic model-folder discovery."""

    raw_path = (
        cfg.get_model_output_dir(region, scenario)
        / "RawResults.csv"
    )

    if raw_path.exists():
        return raw_path

    raise FileNotFoundError(
        f"Could not find RawResults.csv for {region} {scenario}: {raw_path}"
    )

def _find_reg_contributor_path(cfg: GBRConfig, region: str, scenario: str = "BASE") -> Path:
    """Find RegContributorDataGrid for process export rows."""
    filenames = [
        "RegContributorDataGrid.csv",
        "RegContributorDataGrid.CSV",
        "RegionalContributorDataGrid.csv",
        "RegionalContributorDataGrid.CSV",
    ]
    candidates = [folder / filename for folder in _scenario_folders(cfg, region, scenario) for filename in filenames]
    for p in candidates:
        if p.exists():
            return p

    main_path = _cfg_main_path(cfg)
    matches: list[Path] = []
    for filename in filenames:
        matches.extend(main_path.rglob(filename))
    if matches:
        region_upper = region.upper()
        scenario_upper = str(scenario).upper()
        preferred = [p for p in matches if region_upper in str(p).upper() and scenario_upper in str(p).upper()]
        return preferred[0] if preferred else matches[0]

    raise FileNotFoundError("Could not find RegContributorDataGrid. Tried:\n" + "\n".join(str(p) for p in candidates))


def _find_lookup_path(cfg: GBRConfig, region: str) -> Path:
    main_path = _cfg_main_path(cfg)
    candidates = [
        main_path / "regionalisations" / f"{region}_Subcat_Regions_LUT.csv",
        main_path / "Regionalisations" / f"{region}_Subcat_Regions_LUT.csv",
        main_path / region / f"{region}_Subcat_Regions_LUT.csv",
        main_path / f"{region}_Subcat_Regions_LUT.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    matches = list(main_path.rglob(f"{region}_Subcat_Regions_LUT.csv"))
    if matches:
        return matches[0]
    raise FileNotFoundError("Could not find region lookup CSV. Tried:\n" + "\n".join(str(p) for p in candidates))


def _find_reg_cat_node_link_path(
    cfg: GBRConfig,
    region: str,
) -> Path:

    region = str(region).strip().upper()

    return Path(
        package_data_path(
            "region_lookup",
            f"{region}_Reg_cat_node_link.csv",
        )
    )

def _empty_source_sink_outputs() -> dict[str, pd.DataFrame]:
    basin_cols = ["Region", "Scenario", "Basin", "Constituent", "BudgetGroup", DEFAULT_VALUE_COLUMN, "Units", "DisplayValue"]
    region_cols = ["Region", "Scenario", "Constituent", "BudgetGroup", "Units", DEFAULT_VALUE_COLUMN]
    gbr_cols = ["Scenario", "Constituent", "BudgetGroup", "Units", DEFAULT_VALUE_COLUMN]
    return {
        "basin_summary": pd.DataFrame(columns=basin_cols),
        "region_summary": pd.DataFrame(columns=region_cols),
        "gbr_summary": pd.DataFrame(columns=gbr_cols),
    }


def _normalise_selected_constituents(constituents: list[str] | None) -> list[str] | None:
    if constituents is None:
        return None
    return list(standardise_constituent_names(pd.Series(constituents)).dropna().astype(str))


def _standardise_and_filter_constituents(
    df: pd.DataFrame,
    selected_constituents: list[str] | None,
) -> pd.DataFrame:
    out = df.copy()
    if "Constituent" in out.columns:
        out["Constituent"] = standardise_constituent_names(out["Constituent"])
        if selected_constituents is not None:
            out = out.loc[out["Constituent"].isin(selected_constituents)].copy()
    return out


def run_source_sink_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    scenario: str | None = None,
    model: str | None = None,
    process_model: str | None = None,
    units: str = "report",
    basin_column: str = "Manag_Unit_48",
    export_excel_workbook: bool = True,
    require_export_grid: bool = True,
    **kwargs,
) -> dict[str, object]:
    """
    Build source-sink summaries for report-card bundle.

    Correct workflow:
    - RawResults.csv + *_Reg_cat_node_link.csv gives supply/loss terms.
    - RegContributorDataGrid.csv + *_Reg_cat_node_link.csv gives process export terms.
    """
    out_dir = ensure_output_dir(output_dir)

    selected_regions = list(regions if regions is not None else getattr(cfg, "regions", []) or [])
    selected_constituents = _normalise_selected_constituents(constituents)
    selected_scenario = str(scenario or model or process_model or "BASE").upper()

    basin_tables: list[pd.DataFrame] = []
    region_tables: list[pd.DataFrame] = []

    for region in selected_regions:
        raw_path = _find_raw_results_path(cfg=cfg, region=region, scenario=selected_scenario)
        lut_path = _find_reg_cat_node_link_path(cfg=cfg, region=region)

        raw = _standardise_and_filter_constituents(_read_csv(raw_path), selected_constituents)
        lut = _read_csv(lut_path)

        joined = join_raw_results_to_basin_lookup(raw_results=raw, lookup_table=lut)

        basin_summary = build_basin_source_sink_summary_from_raw(
            raw_results=joined,
            region=region,
            scenario=selected_scenario,
            basin_column=basin_column,
            constituent_column="Constituent",
            budget_element_column="BudgetElement",
            value_column=DEFAULT_VALUE_COLUMN,
        )

        try:
            contributor_path = _find_reg_contributor_path(cfg=cfg, region=region, scenario=selected_scenario)
            contributor = _standardise_and_filter_constituents(_read_csv(contributor_path), selected_constituents)
            contributor_joined = join_raw_results_to_basin_lookup(raw_results=contributor, lookup_table=lut)

            export_summary = build_basin_export_summary_from_contributor(
                export_results=contributor_joined,
                region=region,
                scenario=selected_scenario,
                basin_column=basin_column,
                constituent_column="Constituent",
                process_column="Process",
                value_column=DEFAULT_EXPORT_VALUE_COLUMN,
            )

            basin_summary = append_export_groups(
                source_sink_df=basin_summary,
                export_df=export_summary,
                spatial_cols=["Region", "Scenario", "Basin"],
                constituent_col="Constituent",
                value_column=DEFAULT_VALUE_COLUMN,
            )
        except FileNotFoundError:
            if require_export_grid:
                raise
            print(f"WARNING: RegContributorDataGrid not found for {region}; export rows were not added.")

        if basin_summary.empty:
            continue

        if units == "report":
            basin_summary = convert_source_sink_to_annual_units(
                basin_summary,
                model_years=getattr(cfg, "model_years", 30),
                value_column=DEFAULT_VALUE_COLUMN,
            )
        else:
            basin_summary["Units"] = "kg"

        basin_summary = add_display_value(basin_summary, value_column=DEFAULT_VALUE_COLUMN)
        region_summary = build_region_source_sink_summary(
            basin_summary,
            scenario=selected_scenario,
            value_column=DEFAULT_VALUE_COLUMN,
        )

        basin_tables.append(basin_summary)
        region_tables.append(region_summary)

    basin_all = pd.concat(basin_tables, ignore_index=True) if basin_tables else _empty_source_sink_outputs()["basin_summary"]
    region_all = pd.concat(region_tables, ignore_index=True) if region_tables else _empty_source_sink_outputs()["region_summary"]
    gbr_all = build_gbr_source_sink_summary(region_all, value_column=DEFAULT_VALUE_COLUMN) if not region_all.empty else _empty_source_sink_outputs()["gbr_summary"]

    basin_csv = out_dir / "source_sink_basin_summary.csv"
    region_csv = out_dir / "source_sink_region_summary.csv"
    gbr_csv = out_dir / "source_sink_gbr_summary.csv"

    basin_all.to_csv(basin_csv, index=False)
    region_all.to_csv(region_csv, index=False)
    gbr_all.to_csv(gbr_csv, index=False)

    files: dict[str, Path] = {
        "source_sink_summary_csv": basin_csv,
        "region_output_csv": region_csv,
        "gbr_summary_csv": gbr_csv,
    }

    if export_excel_workbook:
        workbook = out_dir / "source_sink_summary.xlsx"
        export_tables_to_excel(
            tables={"basin": basin_all, "region": region_all, "gbr": gbr_all},
            output_path=workbook,
            index=False,
        )
        files["source_sink_workbook"] = workbook

    return {
        "basin_summary": basin_all,
        "region_summary": region_all,
        "gbr_summary": gbr_all,
        "files": files,
    }


def build_source_sink_summary(*args, **kwargs) -> dict[str, object]:
    return run_source_sink_summary(*args, **kwargs)


def export_source_sink_summary(*args, **kwargs) -> dict[str, object]:
    return run_source_sink_summary(*args, **kwargs)


def run_source_sink_sankey_all_basins(
    cfg: GBRConfig,
    output_dir: str | Path,
    scenario: str = "BASE",
    basin_scale: str = "MU48",
    constituents: list[str] | None = None,
    regions: list[str] | None = None,
    **kwargs,
) -> dict[str, object]:
    """Wrapper-compatible Sankey runner for report-card bundle."""
    script_path = Path(__file__).resolve().parent / "run_sankey_all_basins.py"
    if not script_path.exists():
        raise FileNotFoundError(f"Sankey script not found: {script_path}")

    cmd = [
        sys.executable,
        str(script_path),
        "--model",
        str(scenario).upper(),
        "--basin-scale",
        basin_scale,
    ]

    if regions:
        cmd.extend(["--regions", ",".join(regions)])
    if constituents:
        cmd.extend(["--constituents", ",".join(constituents)])

    print("\nRunning Sankey generation")
    print(" ".join(cmd))

    env = dict(os.environ)
    env["GBR_SANKEY_OUTPUT_ROOT"] = str(output_dir)
    if getattr(cfg, "main_path", None):
        env["GBR_BASE_PATH"] = str(getattr(cfg, "main_path"))

    result = subprocess.run(cmd, check=False, capture_output=True, text=True, env=env)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"Sankey generation failed with exit code {result.returncode}")

    return {"files": {"sankey_plot": str(output_dir)}}


def run_source_sink_sankey_for_all_basins(*args, **kwargs) -> dict[str, object]:
    return run_source_sink_sankey_all_basins(*args, **kwargs)


def export_source_sink_sankey_all_basins(*args, **kwargs) -> dict[str, object]:
    return run_source_sink_sankey_all_basins(*args, **kwargs)
