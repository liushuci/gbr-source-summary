"""
Higher-level FU workflows for gbr_source_summary.

This module builds:
- basin FU summaries for selected region(s)/model
- region FU summaries
- GBR-style combined summaries across the selected regions

Supports both basin aggregation scales:
- Basin_35
- Manag_Unit_48
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
    Resolve user-facing basin scale input to the actual lookup column name.

    Parameters
    ----------
    basin_scale : str
        Supported values:
        - "35", "Basin_35", "basin35"
        - "48", "MU_48", "Manag_Unit_48", "management_unit_48"

    Returns
    -------
    str
        Lookup column name used in the LUT/dataframe.
    """
    basin_scale_map = {
        "35": "Basin_35",
        "basin_35": "Basin_35",
        "basin35": "Basin_35",
        "48": "Manag_Unit_48",
        "mu_48": "Manag_Unit_48",
        "manag_unit_48": "Manag_Unit_48",
        "management_unit_48": "Manag_Unit_48",
    }

    basin_key = basin_scale.strip().lower()
    if basin_key not in basin_scale_map:
        raise ValueError(
            "Invalid basin_scale. Use one of: "
            "'35', 'Basin_35', '48', 'MU_48', 'Manag_Unit_48'."
        )

    return basin_scale_map[basin_key]


def build_region_fu_export_summary(
    cfg: GBRConfig,
    region: str,
    model: str,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    basin_scale: str = "48",
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Build basin-level and region-level FU export summaries for one region/model.

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
        Basin aggregation scale.

    Returns
    -------
    tuple
        (
            basin_summary,
            region_summary,
        )

        basin_summary : dict[str, pd.DataFrame]
            Nested mapping of basin -> FU summary dataframe

        region_summary : pd.DataFrame
            Region-level FU summary dataframe
    """
    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    basin_column = resolve_basin_column(basin_scale)

    df = load_reg_contributor_data_grid_with_lut(cfg, region, model)
    df = apply_constituent_name_standardisation(df)

    basin_summary = build_basin_fu_summary(
        df=df,
        constituents=constituents,
        fus_of_interest=cfg.fus_of_interest,
        value_column=value_column,
        basin_column=basin_column,
    )

    region_summary = aggregate_region_fu_summary(basin_summary)

    return basin_summary, region_summary


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
    basin_scale : str, default "48"
        Basin aggregation scale. Supported values:
        - "35" / "Basin_35"
        - "48" / "MU_48" / "Manag_Unit_48"

    Returns
    -------
    tuple
        (
            basin_summaries_by_region,
            region_summaries_by_region,
            combined_summary
        )

        basin_summaries_by_region : dict[str, dict[str, pd.DataFrame]]
            Nested dict of region -> basin -> FU summary dataframe

        region_summaries_by_region : dict[str, pd.DataFrame]
            Region-level FU summaries after unit conversion

        combined_summary : pd.DataFrame
            GBR-combined FU summary after unit conversion
    """
    selected_regions = resolve_regions(cfg, region=region, regions=regions)

    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    basin_summaries_by_region: Dict[str, dict[str, pd.DataFrame]] = {}
    region_summaries_by_region_raw: Dict[str, pd.DataFrame] = {}

    for reg in selected_regions:
        basin_summary, region_summary = build_region_fu_export_summary(
            cfg=cfg,
            region=reg,
            model=model,
            constituents=constituents,
            value_column=value_column,
            basin_scale=basin_scale,
        )
        basin_summaries_by_region[reg] = basin_summary
        region_summaries_by_region_raw[reg] = region_summary

    combined_summary_raw = aggregate_gbr_fu_summary(region_summaries_by_region_raw)

    # Convert and relabel regional summaries
    region_summaries_by_region: Dict[str, pd.DataFrame] = {}
    for reg, df in region_summaries_by_region_raw.items():
        df_units = apply_units(
            df,
            units=units,
            years=cfg.model_years,
        )
        df_units = rename_units_column(
            df_units,
            base_name="LoadToRegExport",
            units=units,
        )
        region_summaries_by_region[reg] = df_units

    # Convert and relabel combined summary
    combined_summary = apply_units(
        combined_summary_raw,
        units=units,
        years=cfg.model_years,
    )
    combined_summary = rename_units_column(
        combined_summary,
        base_name="LoadToRegExport",
        units=units,
    )

    return basin_summaries_by_region, region_summaries_by_region, combined_summary