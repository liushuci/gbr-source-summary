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

Supported grouped aggregation scales:
- Basin_35
- Manag_Unit_48
- WQI
"""

from __future__ import annotations

import pandas as pd

from .comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)
from .config import GBRConfig
from .workflows_fu import build_fu_export_summaries, resolve_basin_column


def build_fu_scenario_comparison(
    cfg: GBRConfig,
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
) -> dict[str, object]:
    """
    Build FU summary tables for PREDEV, BASE, CHANGE and derive scenario comparisons
    at the regional / combined level.

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


def build_fu_grouped_scenario_comparison(
    cfg: GBRConfig,
    basin_scale: str = "48",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
) -> dict[str, object]:
    """
    Build FU scenario comparison tables at a grouped aggregation scale.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    basin_scale : str, default "48"
        Aggregation scale. Supported values include aliases resolving to:
        - Basin_35
        - Manag_Unit_48
        - WQI
    region : str | None
        Single region code.
    regions : list[str] | None
        Multiple region codes.
    constituents : list[str] | None
        Constituents to include.
    value_column : str
        Numeric value column to summarise.
    units : str
        Output units.

    Returns
    -------
    dict[str, object]
        Dictionary containing:
        - predev_grouped
        - base_grouped
        - change_grouped
        - anthropogenic_grouped
        - reduction_grouped
        - percent_reduction_grouped
        - basin_scale

    Notes
    -----
    The nested output structure remains:
        result[region][group_name] = DataFrame

    The key names retain 'grouped' rather than 'basin' because the selected
    grouping may be Basin_35, Manag_Unit_48, or WQI.
    """
    resolved_scale = resolve_basin_column(basin_scale)

    predev_grouped, _, _ = build_fu_export_summaries(
        cfg=cfg,
        model="PREDEV",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        basin_scale=resolved_scale,
    )

    base_grouped, _, _ = build_fu_export_summaries(
        cfg=cfg,
        model="BASE",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        basin_scale=resolved_scale,
    )

    change_grouped, _, _ = build_fu_export_summaries(
        cfg=cfg,
        model="CHANGE",
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        basin_scale=resolved_scale,
    )

    anthropogenic_grouped: dict[str, dict[str, pd.DataFrame]] = {}
    reduction_grouped: dict[str, dict[str, pd.DataFrame]] = {}
    percent_reduction_grouped: dict[str, dict[str, pd.DataFrame]] = {}

    region_keys = sorted(
        set(base_grouped.keys()) | set(predev_grouped.keys()) | set(change_grouped.keys())
    )

    for reg in region_keys:
        anthropogenic_grouped[reg] = {}
        reduction_grouped[reg] = {}
        percent_reduction_grouped[reg] = {}

        base_groups = base_grouped.get(reg, {})
        predev_groups = predev_grouped.get(reg, {})
        change_groups = change_grouped.get(reg, {})

        group_keys = sorted(
            set(base_groups.keys()) | set(predev_groups.keys()) | set(change_groups.keys())
        )

        for group_name in group_keys:
            base_df = base_groups.get(group_name)
            predev_df = predev_groups.get(group_name)
            change_df = change_groups.get(group_name)

            if base_df is None:
                base_df = pd.DataFrame()
            if predev_df is None:
                predev_df = pd.DataFrame()
            if change_df is None:
                change_df = pd.DataFrame()

            anthropogenic_grouped[reg][group_name] = calc_anthropogenic(base_df, predev_df)
            reduction_grouped[reg][group_name] = calc_reduction(base_df, change_df)
            percent_reduction_grouped[reg][group_name] = calc_percent_reduction(
                base_df,
                predev_df,
                change_df,
            )

    return {
        "predev_grouped": predev_grouped,
        "base_grouped": base_grouped,
        "change_grouped": change_grouped,
        "anthropogenic_grouped": anthropogenic_grouped,
        "reduction_grouped": reduction_grouped,
        "percent_reduction_grouped": percent_reduction_grouped,
        "basin_scale": resolved_scale,
    }


def build_fu_basin_scenario_comparison(
    cfg: GBRConfig,
    basin_scale: str = "48",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "kg",
) -> dict[str, object]:
    """
    Backward-compatible wrapper for grouped FU scenario comparison.

    Parameters
    ----------
    basin_scale : str, default "48"
        Aggregation scale. Supported values include aliases resolving to:
        - Basin_35
        - Manag_Unit_48
        - WQI

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
        - basin_scale

    Notes
    -----
    Function name and return keys retain 'basin' for backward compatibility,
    but the selected grouping may also be WQI.
    """
    grouped = build_fu_grouped_scenario_comparison(
        cfg=cfg,
        basin_scale=basin_scale,
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
    )

    return {
        "predev_basin": grouped["predev_grouped"],
        "base_basin": grouped["base_grouped"],
        "change_basin": grouped["change_grouped"],
        "anthropogenic_basin": grouped["anthropogenic_grouped"],
        "reduction_basin": grouped["reduction_grouped"],
        "percent_reduction_basin": grouped["percent_reduction_grouped"],
        "basin_scale": grouped["basin_scale"],
    }


def flatten_basin_tables(
    basin_tables_by_region: dict[str, dict[str, pd.DataFrame]]
) -> pd.DataFrame:
    """
    Flatten nested grouped tables into one long dataframe.

    Parameters
    ----------
    basin_tables_by_region : dict[str, dict[str, pd.DataFrame]]
        Nested structure:
            basin_tables_by_region[Region][GroupName] = DataFrame

    Returns
    -------
    pd.DataFrame
        Columns:
        - Region
        - Basin
        - FU
        - constituent columns...

    Notes
    -----
    The output column name 'Basin' is retained for backward compatibility,
    even though the grouping may represent Basin_35, Manag_Unit_48, or WQI.
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