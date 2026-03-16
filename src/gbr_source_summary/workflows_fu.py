"""
Higher-level FU workflows for gbr_source_summary.

This module builds:
- basin FU summaries for selected region(s)/model
- region FU summaries
- GBR-style combined summaries across the selected regions
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


def build_region_fu_export_summary(
    cfg: GBRConfig,
    region: str,
    model: str,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Build basin-level and region-level FU export summaries for one region/model.
    """
    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

    df = load_reg_contributor_data_grid_with_lut(cfg, region, model)
    df = apply_constituent_name_standardisation(df)

    basin_summary = build_basin_fu_summary(
        df=df,
        constituents=constituents,
        fus_of_interest=cfg.fus_of_interest,
        value_column=value_column,
        basin_column="Manag_Unit_48",
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
) -> tuple[Dict[str, dict[str, pd.DataFrame]], Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    Build FU export summaries for one region, multiple regions, or all GBR regions.
    """
    selected_regions = resolve_regions(cfg, region=region, regions=regions)

    basin_summaries_by_region: Dict[str, dict[str, pd.DataFrame]] = {}
    region_summaries_by_region_raw: Dict[str, pd.DataFrame] = {}

    for reg in selected_regions:
        basin_summary, region_summary = build_region_fu_export_summary(
            cfg=cfg,
            region=reg,
            model=model,
            constituents=constituents,
            value_column=value_column,
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