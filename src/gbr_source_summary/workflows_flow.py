"""
Higher-level flow workflows for gbr_source_summary.

This module builds:
- FU-level flow summaries for selected region(s)/model
- basin-level flow summaries
- combined summaries across selected regions

It connects:
- io.py
- regions.py
- summary_flow.py
- units.py
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from .config import GBRConfig
from .io import load_reg_contributor_data_grid_with_lut
from .regions import resolve_regions
from .summary_flow import (
    build_fu_flow_summary,
    build_basin_flow_summary,
    aggregate_flow_tables,
)
from .units import apply_units,rename_units_column


def build_region_flow_summary(
    cfg: GBRConfig,
    region: str,
    model: str,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "ML",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build FU-level and basin-level flow summaries for one region/model.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    region : str
        Region code.
    model : str
        Model scenario.
    value_column : str
        Numeric column used for flow summarisation.
    units : str
        Target flow units. Supported examples:
        - ML
        - GL
        - ML/yr
        - GL/yr
        - report

    Returns
    -------
    tuple
        (
            fu_flow_summary,
            basin_flow_summary
        )
    """
    df = load_reg_contributor_data_grid_with_lut(cfg, region, model)

    fu_flow = build_fu_flow_summary(
        df=df,
        value_column=value_column,
    )
    basin_flow = build_basin_flow_summary(
        df=df,
        value_column=value_column,
    )

    fu_flow = apply_units(fu_flow, units=units, years=cfg.model_years)
    basin_flow = apply_units(basin_flow, units=units, years=cfg.model_years)

    fu_flow = rename_units_column(fu_flow, "Flow", units)
    basin_flow = rename_units_column(basin_flow, "Flow", units)



    return fu_flow, basin_flow


def build_flow_summaries(
    cfg: GBRConfig,
    model: str,
    region: str | None = None,
    regions: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "ML",
) -> tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """
    Build flow summaries for one region, multiple regions, or all GBR regions.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    model : str
        Model scenario.
    region : str | None
        Single region code.
    regions : list[str] | None
        Multiple region codes.
    value_column : str
        Numeric column used for flow summarisation.
    units : str
        Target units.

    Returns
    -------
    tuple
        (
            fu_flow_by_region,
            basin_flow_by_region,
            combined_fu_flow,
            combined_basin_flow
        )
    """
    selected_regions = resolve_regions(cfg, region=region, regions=regions)

    fu_flow_by_region: Dict[str, pd.DataFrame] = {}
    basin_flow_by_region: Dict[str, pd.DataFrame] = {}

    for reg in selected_regions:
        fu_flow, basin_flow = build_region_flow_summary(
            cfg=cfg,
            region=reg,
            model=model,
            value_column=value_column,
            units=units,
        )
        fu_flow_by_region[reg] = fu_flow
        basin_flow_by_region[reg] = basin_flow

    combined_fu_flow = aggregate_flow_tables(fu_flow_by_region)
    combined_basin_flow = aggregate_flow_tables(basin_flow_by_region)

    return fu_flow_by_region, basin_flow_by_region, combined_fu_flow, combined_basin_flow