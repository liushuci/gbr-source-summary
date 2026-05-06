"""
Higher-level FU workflows for gbr_source_summary.

This module builds:
- grouped FU summaries for selected region(s)/model
- region FU summaries
- GBR-style combined summaries across the selected regions

Supported aggregation scales:
- Basin_35
- Manag_Unit_48
- WQI
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from .config import GBRConfig
from .io import load_reg_contributor_data_grid_with_lut
from .naming import apply_constituent_name_standardisation
from .regions import resolve_regions
from .summary_fu import (
    build_basin_fu_summary,
    aggregate_region_fu_summary,
    aggregate_gbr_fu_summary,
)
from .units import apply_units, rename_units_column


def resolve_basin_column(basin_scale: str) -> str:
    """
    Resolve user-facing aggregation scale input to the actual lookup column name.

    Parameters
    ----------
    basin_scale : str
        Supported values:
        - Basin_35:
            "35", "basin35", "basin_35"
        - Manag_Unit_48:
            "48", "mu48", "mu_48", "manag_unit_48", "management_unit_48"
        - WQI:
            "wqi"

    Returns
    -------
    str
        Lookup column name used in the LUT/dataframe.
        One of:
            - "Basin_35"
            - "Manag_Unit_48"
            - "WQI"
    """
    if basin_scale is None:
        raise ValueError("basin_scale cannot be None")

    key = str(basin_scale).strip().lower()

    basin_scale_map = {
        # Basin 35
        "35": "Basin_35",
        "basin35": "Basin_35",
        "basin_35": "Basin_35",

        # MU48
        "48": "Manag_Unit_48",
        "mu48": "Manag_Unit_48",
        "mu_48": "Manag_Unit_48",
        "manag_unit_48": "Manag_Unit_48",
        "management_unit_48": "Manag_Unit_48",

        # WQI
        "wqi": "WQI",
    }

    if key not in basin_scale_map:
        raise ValueError(
            "Invalid basin_scale. Use one of:\n"
            "  Basin_35: '35', 'basin35', 'basin_35'\n"
            "  Manag_Unit_48: '48', 'mu48', 'mu_48', 'manag_unit_48', 'management_unit_48'\n"
            "  WQI: 'wqi'"
        )

    return basin_scale_map[key]


def _convert_wide_report_units(
    df: pd.DataFrame,
    *,
    model_years: float,
) -> pd.DataFrame:
    """
    Convert FU wide tables from total kg over model period to report-card units.

    Expected input
    --------------
    Wide dataframe with:
    - index = FU
    - columns = constituent names

    Conversion
    ----------
    - FS, CS -> kt/yr
    - all others -> t/yr
    """
    out = df.copy()

    for col in out.columns:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

        if str(col).upper() in {"FS", "CS"}:
            out[col] = out[col] / 1e6 / model_years
        else:
            out[col] = out[col] / 1e3 / model_years

    return out


def build_region_fu_export_summary(
    cfg: GBRConfig,
    region: str,
    model: str,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    basin_scale: str = "48",
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Build grouped and region-level FU export summaries for one region/model.

    Parameters
    ----------
    cfg : GBRConfig
        Central configuration object.
    region : str
        Region code, e.g. CY, WT, BU.
    model : str
        Scenario/model name, e.g. PREDEV, BASE, CHANGE.
    constituents : list[str], optional
        Constituents to include.
    value_column : str, default "LoadToRegExport (kg)"
        Column containing export loads.
    basin_scale : str, default "48"
        Aggregation scale. Supported values resolve to:
        - Basin_35
        - Manag_Unit_48
        - WQI

    Returns
    -------
    tuple
        (
            grouped_summary,
            region_summary,
        )

        grouped_summary : dict[str, pd.DataFrame]
            Nested mapping of aggregation unit -> FU summary dataframe

        region_summary : pd.DataFrame
            Region-level FU summary dataframe
    """
    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    basin_column = resolve_basin_column(basin_scale)

    df = load_reg_contributor_data_grid_with_lut(cfg, region, model)
    df = apply_constituent_name_standardisation(df)

    grouped_summary = build_basin_fu_summary(
        df=df,
        constituents=constituents,
        fus_of_interest=cfg.fus_of_interest,
        value_column=value_column,
        basin_column=basin_column,
    )

    region_summary = aggregate_region_fu_summary(grouped_summary)

    return grouped_summary, region_summary


def build_fu_export_summaries(
    cfg: GBRConfig,
    model: str,
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
    basin_scale: str = "48",
) -> tuple[Dict[str, dict[str, pd.DataFrame]], Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Build FU export summaries for one region, multiple regions, or all GBR regions.

    Parameters
    ----------
    cfg : GBRConfig
        Central configuration object.
    model : str
        Scenario/model name, e.g. PREDEV, BASE, CHANGE.
    region : str, optional
        Single region to process.
    regions : list[str], optional
        Multiple regions to process.
    constituents : list[str], optional
        Constituents to include.
    value_column : str, default "LoadToRegExport (kg)"
        Column containing export loads.
    units : str, default "kg"
        Output units passed to apply_units().
        Special case:
        - "report" is handled here directly for wide FU tables
    basin_scale : str, default "48"
        Aggregation scale. Supported values resolve to:
        - Basin_35
        - Manag_Unit_48
        - WQI

    Returns
    -------
    tuple
        (
            grouped_summaries_by_region,
            region_summaries_by_region,
            combined_summary
        )

        grouped_summaries_by_region : dict[str, dict[str, pd.DataFrame]]
            Nested dict of region -> aggregation unit -> FU summary dataframe

        region_summaries_by_region : dict[str, pd.DataFrame]
            Region-level FU summaries after unit conversion

        combined_summary : pd.DataFrame
            GBR-combined FU summary after unit conversion
    """
    selected_regions = resolve_regions(cfg, region=region, regions=regions)

    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    grouped_summaries_by_region: Dict[str, dict[str, pd.DataFrame]] = {}
    region_summaries_by_region_raw: Dict[str, pd.DataFrame] = {}

    for reg in selected_regions:
        grouped_summary, region_summary = build_region_fu_export_summary(
            cfg=cfg,
            region=reg,
            model=model,
            constituents=constituents,
            value_column=value_column,
            basin_scale=basin_scale,
        )
        grouped_summaries_by_region[reg] = grouped_summary
        region_summaries_by_region_raw[reg] = region_summary

    combined_summary_raw = aggregate_gbr_fu_summary(region_summaries_by_region_raw)

    region_summaries_by_region: Dict[str, pd.DataFrame] = {}
    for reg, df in region_summaries_by_region_raw.items():
        if units == "report":
            df_units = _convert_wide_report_units(
                df,
                model_years=cfg.model_years,
            )
        else:
            df_units = apply_units(
                df,
                units=units,
                years=cfg.model_years,
            )

        df_units = rename_units_column(
            df_units,
            base_name="LoadToRegExport",
            units="kt/yr & t/yr" if units == "report" else units,
        )
        region_summaries_by_region[reg] = df_units

    if units == "report":
        combined_summary = _convert_wide_report_units(
            combined_summary_raw,
            model_years=cfg.model_years,
        )
    else:
        combined_summary = apply_units(
            combined_summary_raw,
            units=units,
            years=cfg.model_years,
        )

    combined_summary = rename_units_column(
        combined_summary,
        base_name="LoadToRegExport",
        units="kt/yr & t/yr" if units == "report" else units,
    )

    return grouped_summaries_by_region, region_summaries_by_region, combined_summary