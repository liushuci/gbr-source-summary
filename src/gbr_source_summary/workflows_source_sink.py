from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
import os
from .naming import (
    standardise_constituent_names,
    standardise_management_unit_names,
)
from .units import apply_units


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


def _ensure_required_budget_elements(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure all expected budget elements are present in the index.
    Missing elements are added with zero values.
    """
    out = df.copy()
    out = out.reindex(REQUIRED_BUDGET_ELEMENTS, fill_value=0.0)
    return out


def _normalise_budget_element_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse hillslope variants to a single Hillslope label to match
    the original notebook logic for budget summaries.
    """
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
    """
    Standardise constituent and basin names.
    """
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
    """
    Apply report-card annual units to source-sink outputs using the shared
    units helper.

    FS and CS -> kt/yr
    All others -> t/yr
    """
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

    # Promote CS to kt/yr as well
    cs_mask = out["Constituent"] == "CS"
    if cs_mask.any():
        out.loc[cs_mask, "Units"] = "kt/yr"
        out.loc[cs_mask, value_column] = pd.to_numeric(
            out.loc[cs_mask, value_column],
            errors="coerce",
        ) / 1000.0

    return out


def summarise_basin_budget_for_constituent(
    df_basin_constituent: pd.DataFrame,
    constituent: str,
    region: str,
) -> pd.DataFrame:
    """
    Convert raw basin-level budget rows for a single constituent into the
    grouped source-sink terms used in report-card style summaries.

    Input dataframe is expected to contain:
    - BudgetElement
    - Total_Load_in_Kg
    """
    if df_basin_constituent.empty:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    work = (
        df_basin_constituent.groupby("BudgetElement", dropna=False, as_index=True)[DEFAULT_VALUE_COLUMN]
        .sum()
        .to_frame()
    )

    work[DEFAULT_VALUE_COLUMN] = pd.to_numeric(
        work[DEFAULT_VALUE_COLUMN],
        errors="coerce",
    ).fillna(0.0)

    work = _ensure_required_budget_elements(work)

    def val(name: str) -> float:
        return float(work.loc[name, DEFAULT_VALUE_COLUMN]) if name in work.index else 0.0

    rows: list[dict[str, object]] = []

    if constituent in SEDIMENT_PARTICULATE_CONSTITUENTS:
        hillslope = val("Hillslope")
        undefined = val("Undefined")

        # Preserve existing region-specific FS handling
        if constituent == "FS":
            if region not in {"CY", "BU", "FI", "BM"}:
                hillslope = hillslope + undefined
        else:
            hillslope = hillslope + undefined

        rows = [
            {"BudgetGroup": "Hillslope", DEFAULT_VALUE_COLUMN: hillslope},
            {"BudgetGroup": "Streambank", DEFAULT_VALUE_COLUMN: val("Streambank")},
            {"BudgetGroup": "Gully", DEFAULT_VALUE_COLUMN: val("Gully")},
            {
                "BudgetGroup": "ChannelRemobilisation",
                DEFAULT_VALUE_COLUMN: val("Channel Remobilisation"),
            },
            {
                "BudgetGroup": "Extraction + Other Minor Losses",
                DEFAULT_VALUE_COLUMN: (
                    val("Extraction")
                    + val("Node Loss")
                    + val("Residual Link Storage")
                    + val("Residual Node Storage")
                ),
            },
            {
                "BudgetGroup": "FloodPlainDeposition",
                DEFAULT_VALUE_COLUMN: val("Flood Plain Deposition"),
            },
            {
                "BudgetGroup": "ReservoirDeposition",
                DEFAULT_VALUE_COLUMN: val("Reservoir Deposition"),
            },
            {
                "BudgetGroup": "StreamDeposition",
                DEFAULT_VALUE_COLUMN: val("Stream Deposition"),
            },
        ]

    elif constituent in DISSOLVED_CONSTITUENTS:
        # Preserve existing DIN logic and apply same dissolved-nutrient structure
        # to DON, DIP and DOP
        if constituent == "DIN":
            if region in {"CY", "BU", "BM"}:
                surface_runoff = val("Diffuse Dissolved") + val("Hillslope")
            elif region == "FI":
                surface_runoff = val("Diffuse Dissolved")
            else:
                surface_runoff = (
                    val("Undefined")
                    + val("Diffuse Dissolved")
                    + val("Hillslope")
                )
        else:
            surface_runoff = (
                val("Undefined")
                + val("Diffuse Dissolved")
                + val("Hillslope")
            )

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


def summarise_export_for_constituent(
    df_export_constituent: pd.DataFrame,
    constituent: str,
    value_column: str = DEFAULT_EXPORT_VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Convert process export rows for a single constituent into grouped
    export terms that match the source groups used in Sankey plots.

    Input dataframe is expected to contain:
    - Process
    - LoadToRegExport (kg) or equivalent value_column

    Output BudgetGroup values:
    - HillslopeExport
    - StreambankExport
    - GullyExport
    - ChannelRemobilisationExport
    - SurfaceRunoffExport
    - SeepageExport
    - PointSourceExport
    """
    if df_export_constituent.empty:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    work = (
        df_export_constituent.groupby("Process", dropna=False, as_index=True)[value_column]
        .sum()
        .to_frame()
    )

    work[value_column] = pd.to_numeric(
        work[value_column],
        errors="coerce",
    ).fillna(0.0)

    def val(name: str) -> float:
        return float(work.loc[name, value_column]) if name in work.index else 0.0

    rows: list[dict[str, object]]

    if constituent in SEDIMENT_PARTICULATE_CONSTITUENTS:
        if constituent == "FS":
            hillslope_export = val("Hillslope surface soil") + val("Undefined")
        else:
            hillslope_export = val("Hillslope no source distinction") + val("Undefined")

        rows = [
            {"BudgetGroup": "HillslopeExport", DEFAULT_VALUE_COLUMN: hillslope_export},
            {"BudgetGroup": "StreambankExport", DEFAULT_VALUE_COLUMN: val("Streambank")},
            {"BudgetGroup": "GullyExport", DEFAULT_VALUE_COLUMN: val("Gully")},
            {
                "BudgetGroup": "ChannelRemobilisationExport",
                DEFAULT_VALUE_COLUMN: val("Channel Remobilisation"),
            },
        ]

    elif constituent in DISSOLVED_CONSTITUENTS:
        rows = [
            {
                "BudgetGroup": "SurfaceRunoffExport",
                DEFAULT_VALUE_COLUMN: (
                    val("Undefined")
                    + val("Diffuse Dissolved")
                    + val("Hillslope no source distinction")
                ),
            },
            {"BudgetGroup": "SeepageExport", DEFAULT_VALUE_COLUMN: val("Seepage")},
            {"BudgetGroup": "PointSourceExport", DEFAULT_VALUE_COLUMN: val("Point Source")},
        ]

    else:
        return pd.DataFrame(columns=["BudgetGroup", DEFAULT_VALUE_COLUMN])

    out = pd.DataFrame(rows)
    out["Constituent"] = constituent
    return out


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
    """
    Generic builder for source-sink summaries grouped by one spatial column.
    """
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
    work[DEFAULT_VALUE_COLUMN] = pd.to_numeric(
        work[DEFAULT_VALUE_COLUMN],
        errors="coerce",
    ).fillna(0.0)

    work = work.loc[work[group_name].notna()].copy()
    work[group_name] = work[group_name].astype(str).str.strip()
    work = work.loc[work["Constituent"].isin(SOURCE_SINK_CONSTITUENTS)].copy()

    rows: list[pd.DataFrame] = []

    grouped = work.groupby([group_name, "Constituent"], dropna=False)

    for (group_value, constituent), df_gc in grouped:
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

    if not rows:
        return pd.DataFrame(
            columns=[
                "Region",
                "Scenario",
                group_name,
                "Constituent",
                "BudgetGroup",
                DEFAULT_VALUE_COLUMN,
                "Units",
            ]
        )

    out = pd.concat(rows, ignore_index=True)
    out = out[
        [
            "Region",
            "Scenario",
            group_name,
            "Constituent",
            "BudgetGroup",
            DEFAULT_VALUE_COLUMN,
            "Units",
        ]
    ]

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
    """
    Generic builder for grouped export summaries from process export data
    (e.g. RegContributorDataGrid already joined to LUT).

    Output uses BudgetGroup values such as:
    - HillslopeExport
    - StreambankExport
    - GullyExport
    - ChannelRemobilisationExport
    - SurfaceRunoffExport
    - SeepageExport
    - PointSourceExport
    """
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
    work[DEFAULT_VALUE_COLUMN] = pd.to_numeric(
        work[DEFAULT_VALUE_COLUMN],
        errors="coerce",
    ).fillna(0.0)

    work = work.loc[work[group_name].notna()].copy()
    work[group_name] = work[group_name].astype(str).str.strip()
    work = work.loc[work["Constituent"].isin(SOURCE_SINK_CONSTITUENTS)].copy()

    rows: list[pd.DataFrame] = []

    grouped = work.groupby([group_name, "Constituent"], dropna=False)

    for (group_value, constituent), df_gc in grouped:
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

    if not rows:
        return pd.DataFrame(
            columns=[
                "Region",
                "Scenario",
                group_name,
                "Constituent",
                "BudgetGroup",
                DEFAULT_VALUE_COLUMN,
                "Units",
            ]
        )

    out = pd.concat(rows, ignore_index=True)
    out = out[
        [
            "Region",
            "Scenario",
            group_name,
            "Constituent",
            "BudgetGroup",
            DEFAULT_VALUE_COLUMN,
            "Units",
        ]
    ]

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
    """
    Build subcatchment source-sink summary from raw results.
    """
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
    """
    Build basin source-sink summary from raw results already joined to basin lookup.
    """
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
    """
    Build subcatchment export summary from contributor/process export rows.
    """
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
    """
    Build basin export summary from contributor/process export rows already joined to basin lookup.
    """
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


def append_export_groups(
    source_sink_df: pd.DataFrame,
    export_df: pd.DataFrame,
    *,
    spatial_cols: list[str],
    constituent_col: str = "Constituent",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Append source-specific export rows to an existing source-sink summary table.

    Parameters
    ----------
    source_sink_df
        Existing long-format source-sink summary with BudgetGroup rows.
    export_df
        Long-format export table already grouped to the same spatial scale.
    spatial_cols
        Spatial identifier columns matching the source_sink_df scale.
    """
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

    out = source_sink_df.copy()
    exp = export_df.copy()

    exp[value_column] = pd.to_numeric(exp[value_column], errors="coerce").fillna(0.0)
    exp = exp.loc[exp["BudgetGroup"].isin(EXPORT_BUDGET_GROUPS)].copy()

    if exp.empty:
        return out

    if "Units" not in exp.columns:
        if "Units" in out.columns and not out["Units"].dropna().empty:
            exp["Units"] = out["Units"].dropna().iloc[0]
        else:
            exp["Units"] = "kg"

    common_cols = [c for c in out.columns if c in exp.columns]
    exp = exp[common_cols].copy()

    combined = pd.concat([out, exp], ignore_index=True)

    dedupe_cols = [c for c in combined.columns if c != value_column]
    combined = (
        combined.groupby(dedupe_cols, dropna=False, as_index=False)[value_column]
        .sum()
    )

    return combined


def build_region_source_sink_summary(
    basin_source_sink: pd.DataFrame,
    scenario: str = "BASE",
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Aggregate basin source-sink summary to region level.
    """
    required = ["Region", "Scenario", "Constituent", "BudgetGroup", "Units", value_column]
    missing = [c for c in required if c not in basin_source_sink.columns]
    if missing:
        raise KeyError(f"Missing required columns in basin_source_sink: {missing}")

    work = basin_source_sink.copy()
    work = work.loc[work["Scenario"] == scenario].copy()

    out = (
        work.groupby(
            ["Region", "Scenario", "Constituent", "BudgetGroup", "Units"],
            dropna=False,
            as_index=False,
        )[value_column]
        .sum()
    )

    return out


def build_gbr_source_sink_summary(
    region_source_sink: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Aggregate region source-sink summary to GBR level.
    """
    required = ["Scenario", "Constituent", "BudgetGroup", "Units", value_column]
    missing = [c for c in required if c not in region_source_sink.columns]
    if missing:
        raise KeyError(f"Missing required columns in region_source_sink: {missing}")

    out = (
        region_source_sink.groupby(
            ["Scenario", "Constituent", "BudgetGroup", "Units"],
            dropna=False,
            as_index=False,
        )[value_column]
        .sum()
    )

    return out


def convert_source_sink_to_annual_units(
    df: pd.DataFrame,
    model_years: float,
    value_column: str = DEFAULT_VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Convert source-sink kg totals over model period to annual report-card units.
    """
    return _apply_source_sink_report_units(
        df=df,
        model_years=model_years,
        value_column=value_column,
    )


def add_display_value(
    df: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
    group_column: str = "BudgetGroup",
) -> pd.DataFrame:
    """
    Add signed DisplayValue for plotting / QA.

    Supply groups stay positive.
    Loss groups become negative.
    Export groups become negative.
    """
    required = [group_column, value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing required columns for add_display_value: {missing}")

    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)
    out["DisplayValue"] = out[value_column]

    neg_groups = LOSS_BUDGET_GROUPS | EXPORT_BUDGET_GROUPS
    neg_mask = out[group_column].isin(neg_groups)
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
    """
    Convert grouped source-sink summary to Sankey links.

    Supply groups: BudgetGroup -> central_node
    Loss/export groups: central_node -> BudgetGroup
    """
    required = [group_column, value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"Missing required columns for build_sankey_links_from_summary: {missing}"
        )

    work = df.copy()
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce").fillna(0.0)

    links: list[dict[str, object]] = []

    for _, row in work.iterrows():
        group = row[group_column]
        value = abs(float(row[value_column]))

        if value == 0:
            continue

        if group in LOSS_BUDGET_GROUPS or group in EXPORT_BUDGET_GROUPS:
            links.append(
                {
                    "source": central_node,
                    "target": group,
                    "value": value,
                    "BudgetGroup": group,
                }
            )
        else:
            links.append(
                {
                    "source": group,
                    "target": central_node,
                    "value": value,
                    "BudgetGroup": group,
                }
            )

    return pd.DataFrame(links)


def check_source_sink_balance(
    df: pd.DataFrame,
    value_column: str = DEFAULT_VALUE_COLUMN,
    group_column: str = "BudgetGroup",
) -> float:
    """
    Simple QA helper for source-sink summaries using signed display values.
    Returns the net balance.
    """
    work = add_display_value(
        df=df,
        value_column=value_column,
        group_column=group_column,
    )

    return float(work["DisplayValue"].sum())


def read_raw_results_table(raw_results_path: str | Path) -> pd.DataFrame:
    """
    Read RawResults.csv for a scenario/model output.
    """
    return pd.read_csv(raw_results_path)


def read_region_lookup_table(lookup_path: str | Path) -> pd.DataFrame:
    """
    Read basin/management-unit lookup used to join ModelElement to basin.
    """
    return pd.read_csv(lookup_path)


def join_raw_results_to_basin_lookup(
    raw_results: pd.DataFrame,
    lookup_table: pd.DataFrame,
    raw_model_element_col: str = "ModelElement",
    lookup_model_element_col: str | None = None,
) -> pd.DataFrame:
    """
    Join raw results to the basin lookup table.

    Auto-detects lookup key if ModelElement is not present.
    Common LUT keys include:
    - ModelElement
    - Reg_SC
    - SUBCAT
    - Subcatchment
    """
    if raw_model_element_col not in raw_results.columns:
        raise KeyError(
            f"Missing raw model element column: {raw_model_element_col}. "
            f"Raw columns: {list(raw_results.columns)}"
        )

    lut = lookup_table.copy()

    if lookup_model_element_col is None:
        candidates = [
            "ModelElement",
            "Reg_SC",
            "SUBCAT",
            "Subcat",
            "Subcatchment",
            "Model_Element",
        ]

        for c in candidates:
            if c in lut.columns:
                lookup_model_element_col = c
                break

    if lookup_model_element_col is None or lookup_model_element_col not in lut.columns:
        raise KeyError(
            "Could not find lookup model element column. "
            f"LUT columns: {list(lut.columns)}"
        )

    raw = raw_results.copy()

    raw["_join_model_element"] = (
        raw[raw_model_element_col]
        .astype(str)
        .str.strip()
    )

    lut["_join_model_element"] = (
        lut[lookup_model_element_col]
        .astype(str)
        .str.strip()
    )

    out = pd.merge(
        raw,
        lut,
        on="_join_model_element",
        how="left",
        suffixes=("", "_lut"),
    )

    out = out.drop(columns=["_join_model_element"])

    return out


def build_basin_source_sink_for_region_scenarios(
    region: str,
    scenarios: Iterable[str],
    raw_results_by_scenario: dict[str, pd.DataFrame],
    basin_lookup: pd.DataFrame,
    basin_column: str = "Manag_Unit_48",
) -> pd.DataFrame:
    """
    Convenience wrapper to build one long basin source-sink table for a region
    across multiple scenarios.

    This builds budget-based source/sink rows only.
    Use append_export_groups() separately if you also want export rows included.
    """
    rows: list[pd.DataFrame] = []

    for scenario in scenarios:
        if scenario not in raw_results_by_scenario:
            raise KeyError(f"Missing raw results for scenario: {scenario}")

        raw_results = raw_results_by_scenario[scenario]
        joined = join_raw_results_to_basin_lookup(
            raw_results=raw_results,
            lookup_table=basin_lookup,
        )

        basin_summary = build_basin_source_sink_summary_from_raw(
            raw_results=joined,
            region=region,
            scenario=scenario,
            basin_column=basin_column,
            constituent_column="Constituent",
            budget_element_column="BudgetElement",
            value_column=DEFAULT_VALUE_COLUMN,
        )
        rows.append(basin_summary)

    if not rows:
        return pd.DataFrame(
            columns=[
                "Region",
                "Scenario",
                "Basin",
                "Constituent",
                "BudgetGroup",
                DEFAULT_VALUE_COLUMN,
                "Units",
            ]
        )

    return pd.concat(rows, ignore_index=True)

# =============================================================================
# Wrapper-ready runners
# =============================================================================

from functools import lru_cache

from .config import GBRConfig
from .export import ensure_output_dir
from .export_excel import export_tables_to_excel


@lru_cache(maxsize=None)
def _read_csv_cached(path_str: str) -> pd.DataFrame:
    """
    Cached CSV reader used by the wrapper-level source-sink workflow.

    on_bad_lines='skip' is intentional here so a malformed row in large Source
    output tables does not stop the whole report-card bundle.
    """
    return pd.read_csv(
        path_str,
        low_memory=False,
        on_bad_lines="skip",
    )


def _read_csv(path: str | Path) -> pd.DataFrame:
    return _read_csv_cached(str(path))


def _cfg_rc_label(cfg: GBRConfig) -> str:
    """
    Return the RC/build label used in model output folder names.
    Common examples: Gold_93_23.
    """
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


def _find_raw_results_path(
    cfg: GBRConfig,
    region: str,
    scenario: str = "BASE",
) -> Path:
    """
    Locate RawResults.csv for one region/scenario.
    """
    scenario = str(scenario).upper()
    rc_label = _cfg_rc_label(cfg)
    main_path = _cfg_main_path(cfg)

    candidates = [
        main_path
        / "Gold_ResultsSets_PointOfTruth"
        / region
        / "Model_Outputs"
        / f"{scenario}_{rc_label}"
        / "RawResults.csv",
        main_path
        / region
        / "Model_Outputs"
        / f"{scenario}_{rc_label}"
        / "RawResults.csv",
        main_path
        / "Model_Outputs"
        / region
        / f"{scenario}_{rc_label}"
        / "RawResults.csv",
    ]

    for p in candidates:
        if p.exists():
            return p

    raise FileNotFoundError(
        "Could not find RawResults.csv. Tried:\n"
        + "\n".join(str(p) for p in candidates)
    )


def _find_lookup_path(
    cfg: GBRConfig,
    region: str,
) -> Path:
    """
    Locate region subcatchment-to-basin lookup table.
    """
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

    # Last-resort recursive search. Kept after explicit candidates so it is not
    # expensive during normal runs.
    matches = list(main_path.rglob(f"{region}_Subcat_Regions_LUT.csv"))
    if matches:
        return matches[0]

    raise FileNotFoundError(
        "Could not find region lookup CSV. Tried:\n"
        + "\n".join(str(p) for p in candidates)
    )


def _find_reg_cat_node_link_path(
    cfg: GBRConfig,
    region: str,
) -> Path:
    """
    Locate the region ModelElement-to-basin/management-unit lookup table.

    Source-sink RawResults.csv contains gauges, outlet nodes, reservoirs,
    links and "Node on catchment SC #..." elements, so it must be joined
    to *_Reg_cat_node_link.csv rather than *_Subcat_Regions_LUT.csv.
    """
    main_path = _cfg_main_path(cfg)

    candidates = [
        main_path / "regionalisations" / f"{region}_Reg_cat_node_link.csv",
        main_path / "Regionalisations" / f"{region}_Reg_cat_node_link.csv",
        main_path / region / f"{region}_Reg_cat_node_link.csv",
        main_path / f"{region}_Reg_cat_node_link.csv",
    ]

    for p in candidates:
        if p.exists():
            return p

    # Last-resort recursive search. Kept after explicit candidates so it is not
    # expensive during normal runs.
    matches = list(main_path.rglob(f"{region}_Reg_cat_node_link.csv"))
    if matches:
        return matches[0]

    raise FileNotFoundError(
        "Could not find region Reg_cat_node_link CSV. Tried:\n"
        + "\n".join(str(p) for p in candidates)
    )


def _empty_source_sink_outputs() -> dict[str, pd.DataFrame]:
    basin_cols = [
        "Region",
        "Scenario",
        "Basin",
        "Constituent",
        "BudgetGroup",
        DEFAULT_VALUE_COLUMN,
        "Units",
        "DisplayValue",
    ]
    region_cols = [
        "Region",
        "Scenario",
        "Constituent",
        "BudgetGroup",
        "Units",
        DEFAULT_VALUE_COLUMN,
    ]
    gbr_cols = [
        "Scenario",
        "Constituent",
        "BudgetGroup",
        "Units",
        DEFAULT_VALUE_COLUMN,
    ]
    return {
        "basin_summary": pd.DataFrame(columns=basin_cols),
        "region_summary": pd.DataFrame(columns=region_cols),
        "gbr_summary": pd.DataFrame(columns=gbr_cols),
    }


def _normalise_selected_constituents(
    constituents: list[str] | None,
) -> list[str] | None:
    if constituents is None:
        return None
    return list(standardise_constituent_names(pd.Series(constituents)).dropna().astype(str))


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
    **kwargs,
) -> dict[str, object]:
    """
    Build source-sink summaries for the report-card bundle wrapper.

    This runner intentionally uses RawResults.csv + the region
    *_Reg_cat_node_link.csv lookup directly. It does not require
    RegContributorDataGrid.

    Outputs
    -------
    - source_sink_basin_summary.csv
    - source_sink_region_summary.csv
    - source_sink_gbr_summary.csv
    - source_sink_summary.xlsx, unless disabled
    """
    out_dir = ensure_output_dir(output_dir)

    selected_regions = regions if regions is not None else getattr(cfg, "regions", [])
    selected_regions = list(selected_regions or [])
    selected_constituents = _normalise_selected_constituents(constituents)

    selected_scenario = scenario or model or process_model or "BASE"
    selected_scenario = str(selected_scenario).upper()

    basin_tables: list[pd.DataFrame] = []
    region_tables: list[pd.DataFrame] = []

    for region in selected_regions:
        #print(f"\nLoading source-sink inputs: {region}")

        raw_path = _find_raw_results_path(
            cfg=cfg,
            region=region,
            scenario=selected_scenario,
        )
        lut_path = _find_reg_cat_node_link_path(
            cfg=cfg,
            region=region,
        )

        raw = _read_csv(raw_path)
        lut = _read_csv(lut_path)

        if "Constituent" in raw.columns:
            raw = raw.copy()
            raw["Constituent"] = standardise_constituent_names(raw["Constituent"])
            if selected_constituents is not None:
                raw = raw.loc[raw["Constituent"].isin(selected_constituents)].copy()

        joined = join_raw_results_to_basin_lookup(
            raw_results=raw,
            lookup_table=lut,
        )

        basin_summary = build_basin_source_sink_summary_from_raw(
            raw_results=joined,
            region=region,
            scenario=selected_scenario,
            basin_column=basin_column,
            constituent_column="Constituent",
            budget_element_column="BudgetElement",
            value_column=DEFAULT_VALUE_COLUMN,
        )

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

        basin_summary = add_display_value(
            basin_summary,
            value_column=DEFAULT_VALUE_COLUMN,
        )

        region_summary = build_region_source_sink_summary(
            basin_summary,
            scenario=selected_scenario,
            value_column=DEFAULT_VALUE_COLUMN,
        )

        basin_tables.append(basin_summary)
        region_tables.append(region_summary)

    if basin_tables:
        basin_all = pd.concat(basin_tables, ignore_index=True)
    else:
        basin_all = _empty_source_sink_outputs()["basin_summary"]

    if region_tables:
        region_all = pd.concat(region_tables, ignore_index=True)
    else:
        region_all = _empty_source_sink_outputs()["region_summary"]

    if not region_all.empty:
        gbr_all = build_gbr_source_sink_summary(
            region_all,
            value_column=DEFAULT_VALUE_COLUMN,
        )
    else:
        gbr_all = _empty_source_sink_outputs()["gbr_summary"]

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
            tables={
                "basin": basin_all,
                "region": region_all,
                "gbr": gbr_all,
            },
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
    """
    Alias used by the reflective report-card wrapper.
    """
    return run_source_sink_summary(*args, **kwargs)


def export_source_sink_summary(*args, **kwargs) -> dict[str, object]:
    """
    Alias used by the reflective report-card wrapper.
    """
    return run_source_sink_summary(*args, **kwargs)


def run_source_sink_sankey_all_basins(*args, **kwargs):
    """
    Placeholder for the bundle Sankey step.

    Sankey plotting should remain in the dedicated Sankey script/workflow.
    Keeping this as NotImplementedError lets run_report_card_bundle mark the
    step as SKIPPED unless --fail-fast is used.
    """
    raise NotImplementedError(
        "Sankey export is not wired into workflows_source_sink.py yet. "
        "Run scripts/run_source_sink_sankey_for_basin.py or the dedicated all-basins Sankey script."
    )


def run_source_sink_sankey_for_all_basins(*args, **kwargs):
    """
    Alias used by the reflective report-card wrapper.
    """
    return run_source_sink_sankey_all_basins(*args, **kwargs)


def export_source_sink_sankey_all_basins(*args, **kwargs):
    """
    Alias used by the reflective report-card wrapper.
    """
    return run_source_sink_sankey_all_basins(*args, **kwargs)



def run_source_sink_sankey_all_basins(
    cfg,
    output_dir,
    scenario: str = "BASE",
    basin_scale: str = "MU48",
    constituents: list[str] | None = None,
    regions: list[str] | None = None,
    **kwargs,
):
    """
    Wrapper-compatible Sankey runner for report-card bundle.
    """

    from pathlib import Path
    import subprocess
    import sys

    script_path = Path(__file__).resolve().parent / "run_sankey_all_basins.py"

    if not script_path.exists():
        raise FileNotFoundError(
            f"Sankey script not found: {script_path}"
        )

    cmd = [
        sys.executable,
        str(script_path),
    ]

    print("\nRunning Sankey generation")
    print(" ".join(cmd))

    env = dict(os.environ)
    env["GBR_SANKEY_OUTPUT_ROOT"] = str(output_dir)
    result = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    print(result.stdout)

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(
            f"Sankey generation failed with exit code {result.returncode}"
        )

    return {
        "files": {
            "sankey_plot": str(output_dir)
        }
    }


def run_source_sink_sankey_for_all_basins(*args, **kwargs):
    return run_source_sink_sankey_all_basins(*args, **kwargs)


def export_source_sink_sankey_all_basins(*args, **kwargs):
    return run_source_sink_sankey_all_basins(*args, **kwargs)