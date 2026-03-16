"""
Scenario comparison workflows for gbr_source_summary.

This module builds comparison outputs across the standard GBR scenarios:
- PREDEV
- BASE
- CHANGE

Typical outputs:
- anthropogenic = BASE - PREDEV
- reduction = BASE - CHANGE
- percent reduction = reduction / anthropogenic * 100
"""

from __future__ import annotations

import pandas as pd

from .comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)
from .config import GBRConfig
from .workflows_fu import build_fu_export_summaries


def build_fu_scenario_comparison(
    cfg: GBRConfig,
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
) -> dict[str, object]:
    """
    Build FU summary tables for PREDEV, BASE, CHANGE and derive scenario comparisons.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    region : str | None
        Single region code.
    regions : list[str] | None
        Multiple region codes.
    constituents : list[str] | None
        Constituents to include.
    value_column : str
        Numeric value column to summarise.
    units : str
        Output units. Examples:
        - "kg"
        - "t/yr"
        - "kt/yr"
        - "report"

    Returns
    -------
    dict[str, object]
        Dictionary containing:
        - predev_region
        - base_region
        - change_region
        - predev
        - base
        - change
        - anthropogenic
        - reduction
        - percent_reduction
    """
    _, predev_region, predev_combined = build_fu_export_summaries(
        cfg=cfg,
        model="PREDEV",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    _, base_region, base_combined = build_fu_export_summaries(
        cfg=cfg,
        model="BASE",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    _, change_region, change_combined = build_fu_export_summaries(
        cfg=cfg,
        model="CHANGE",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    anthropogenic = calc_anthropogenic(base_combined, predev_combined)
    reduction = calc_reduction(base_combined, change_combined)
    percent_reduction = calc_percent_reduction(
        base_combined,
        predev_combined,
        change_combined,
    )

    return {
        "predev_region": predev_region,
        "base_region": base_region,
        "change_region": change_region,
        "predev": predev_combined,
        "base": base_combined,
        "change": change_combined,
        "anthropogenic": anthropogenic,
        "reduction": reduction,
        "percent_reduction": percent_reduction,
    }


def build_fu_basin_scenario_comparison(
    cfg: GBRConfig,
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
) -> dict[str, object]:
    """
    Build FU scenario comparison tables at basin (management unit) level.

    Returns
    -------
    dict[str, object]
        Dictionary containing:
        - predev_basin
        - base_basin
        - change_basin
        - anthropogenic_basin
        - reduction_basin
        - percent_reduction_basin
    """
    predev_basin, _, _ = build_fu_export_summaries(
        cfg=cfg,
        model="PREDEV",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    base_basin, _, _ = build_fu_export_summaries(
        cfg=cfg,
        model="BASE",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    change_basin, _, _ = build_fu_export_summaries(
        cfg=cfg,
        model="CHANGE",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    anthropogenic_basin: dict[str, dict[str, pd.DataFrame]] = {}
    reduction_basin: dict[str, dict[str, pd.DataFrame]] = {}
    percent_reduction_basin: dict[str, dict[str, pd.DataFrame]] = {}

    for reg in base_basin:
        anthropogenic_basin[reg] = {}
        reduction_basin[reg] = {}
        percent_reduction_basin[reg] = {}

        for basin in base_basin[reg]:
            base_df = base_basin[reg][basin]
            predev_df = predev_basin[reg][basin]
            change_df = change_basin[reg][basin]

            anthropogenic_basin[reg][basin] = calc_anthropogenic(base_df, predev_df)
            reduction_basin[reg][basin] = calc_reduction(base_df, change_df)
            percent_reduction_basin[reg][basin] = calc_percent_reduction(
                base_df,
                predev_df,
                change_df,
            )

    return {
        "predev_basin": predev_basin,
        "base_basin": base_basin,
        "change_basin": change_basin,
        "anthropogenic_basin": anthropogenic_basin,
        "reduction_basin": reduction_basin,
        "percent_reduction_basin": percent_reduction_basin,
    }


def flatten_basin_tables(
    basin_tables_by_region: dict[str, dict[str, pd.DataFrame]]
) -> pd.DataFrame:
    """
    Flatten nested basin tables into one long dataframe.

    Returns
    -------
    pd.DataFrame
        Columns:
        - Region
        - Basin
        - FU
        - constituent columns...
    """
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