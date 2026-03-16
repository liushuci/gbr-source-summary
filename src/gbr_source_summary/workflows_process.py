"""
Higher-level process workflows for gbr_source_summary.

This module builds:
- basin process summaries for selected region(s)/model
- region process summaries
- GBR-style combined summaries across the selected regions

It connects:
- io.py
- naming.py
- regions.py
- summary_process.py
- units.py
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from .config import GBRConfig
from .io import load_reg_contributor_data_grid_with_lut
from .naming import apply_constituent_name_standardisation
from .regions import resolve_regions
from .summary_process import (
    build_basin_process_summary,
    aggregate_region_process_summary,
    aggregate_gbr_process_summary,
)
from .units import apply_units, rename_units_column


def _convert_process_summary_dict(
    summary_dict: dict[str, pd.DataFrame],
    *,
    units: str,
    years: int,
    base_name: str = "LoadToRegExport",
) -> dict[str, pd.DataFrame]:
    """
    Apply unit conversion and relabel the single value column for each constituent table.
    """
    out: dict[str, pd.DataFrame] = {}

    for constituent, df in summary_dict.items():
        if df.empty:
            out[constituent] = df.copy()
            continue

        df_units = apply_units(df, units=units, years=years)
        df_units = rename_units_column(df_units, base_name=base_name, units=units)
        out[constituent] = df_units

    return out


def build_region_process_export_summary(
    cfg: GBRConfig,
    region: str,
    model: str,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
) -> tuple[dict[str, dict[str, pd.DataFrame]], dict[str, pd.DataFrame]]:
    """
    Build basin-level and region-level process export summaries for one region/model.

    Returns
    -------
    tuple
        (
            basin_summary_dict,
            region_summary_dict
        )
    """
    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN"]

    df = load_reg_contributor_data_grid_with_lut(cfg, region, model)
    df = apply_constituent_name_standardisation(df)

    basin_summary = build_basin_process_summary(
        df=df,
        constituents=constituents,
        value_column=value_column,
        basin_column="Manag_Unit_48",
        constituent_column="Constituent",
        process_column="Process",
    )

    region_summary = aggregate_region_process_summary(
        basin_summary=basin_summary,
        constituents=constituents,
    )

    return basin_summary, region_summary


def build_process_export_summaries(
    cfg: GBRConfig,
    model: str,
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
) -> tuple[
    Dict[str, dict[str, dict[str, pd.DataFrame]]],
    Dict[str, dict[str, pd.DataFrame]],
    dict[str, pd.DataFrame],
]:
    """
    Build process export summaries for one region, multiple regions, or all GBR regions.

    Returns
    -------
    tuple
        (
            basin_summaries_by_region,
            region_summaries_by_region,
            combined_summary
        )
    """
    selected_regions = resolve_regions(cfg, region=region, regions=regions)

    if constituents is None:
        constituents = ["FS", "PN", "PP", "DIN"]

    basin_summaries_by_region: Dict[str, dict[str, dict[str, pd.DataFrame]]] = {}
    region_summaries_by_region_raw: Dict[str, dict[str, pd.DataFrame]] = {}

    for reg in selected_regions:
        basin_summary, region_summary = build_region_process_export_summary(
            cfg=cfg,
            region=reg,
            model=model,
            constituents=constituents,
            value_column=value_column,
        )
        basin_summaries_by_region[reg] = basin_summary
        region_summaries_by_region_raw[reg] = region_summary

    combined_summary_raw = aggregate_gbr_process_summary(
        region_summaries=region_summaries_by_region_raw,
        constituents=constituents,
    )

    region_summaries_by_region: Dict[str, dict[str, pd.DataFrame]] = {}
    for reg, summary_dict in region_summaries_by_region_raw.items():
        region_summaries_by_region[reg] = _convert_process_summary_dict(
            summary_dict,
            units=units,
            years=cfg.model_years,
            base_name="LoadToRegExport",
        )

    combined_summary = _convert_process_summary_dict(
        combined_summary_raw,
        units=units,
        years=cfg.model_years,
        base_name="LoadToRegExport",
    )

    return basin_summaries_by_region, region_summaries_by_region, combined_summary