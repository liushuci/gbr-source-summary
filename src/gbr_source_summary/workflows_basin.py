"""
Basin summary workflows for gbr_source_summary.

Build scenario-wise basin FU summaries using the existing FU workflow.

Supports both basin aggregation scales:
- Basin_35
- Manag_Unit_48
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from .config import GBRConfig
from .comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)
from .workflows_fu import build_fu_export_summaries, resolve_basin_column

def _convert_report_card_units(
    df: pd.DataFrame,
    value_column: str,
    model_years: int,
) -> pd.DataFrame:
    """
    Convert basin long-format load table from total kg over model period
    to report card annual units:
    - FS  -> kt/yr
    - others -> t/yr
    """
    out = df.copy()

    out["Units"] = "t/yr"
    out.loc[out["Constituent"] == "FS", "Units"] = "kt/yr"

    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)

    fs_mask = out["Constituent"] == "FS"
    other_mask = ~fs_mask

    out.loc[fs_mask, value_column] = (
        out.loc[fs_mask, value_column] / 1e6 / model_years
    )
    out.loc[other_mask, value_column] = (
        out.loc[other_mask, value_column] / 1e3 / model_years
    )

    return out


def _add_raw_units(
    df: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    """
    Add raw load units to long-format basin table.
    """
    out = df.copy()
    out["Units"] = "kg"
    return out


def _wide_to_long_with_units(
    df: pd.DataFrame,
    value_name: str,
    reporting_units: str,
    model_years: int,
) -> pd.DataFrame:
    """
    Convert wide comparison dataframe back to long format with units.
    """
    out = df.reset_index().melt(
        id_vars=["Region", "Basin", "BasinScale"],
        var_name="Constituent",
        value_name=value_name,
    )

    if value_name == "PercentReduction":
        out["Units"] = "%"
        return out

    if reporting_units == "report_card":
        out["Units"] = "t/yr"
        fs_mask = out["Constituent"] == "FS"
        out.loc[fs_mask, "Units"] = "kt/yr"

        out[value_name] = out[value_name].astype(float)
        out.loc[fs_mask, value_name] = out.loc[fs_mask, value_name] / 1e6 / model_years
        out.loc[~fs_mask, value_name] = out.loc[~fs_mask, value_name] / 1e3 / model_years
    else:
        out["Units"] = "kg"

    return out

def _stack_basin_summaries(
    basin_summaries_by_region: Dict[str, dict[str, pd.DataFrame]],
    scenario: str,
    value_column: str,
) -> pd.DataFrame:
    """
    Convert nested basin summary dict into one long dataframe.

    Expected structure
    ------------------
    basin_summaries_by_region[region][basin] = DataFrame

    Each basin dataframe is expected to be FU x constituent wide format, e.g.:

                    FS          PN        ...
    FU
    Bananas         ...
    Grazing         ...

    Returns
    -------
    pd.DataFrame
        Long-format dataframe with columns:
            Scenario
            Region
            Basin
            FU
            Constituent
            <value_column>
    """
    rows: list[pd.DataFrame] = []

    for region, basin_dict in basin_summaries_by_region.items():
        for basin, df in basin_dict.items():
            df_long = df.copy()

            # Ensure FU is a column
            if "FU" not in df_long.columns:
                if df_long.index.name == "FU":
                    df_long = df_long.reset_index()
                else:
                    df_long = df_long.reset_index()
                    if "FU" not in df_long.columns:
                        first_col = df_long.columns[0]
                        df_long = df_long.rename(columns={first_col: "FU"})

            df_long["Region"] = region
            df_long["Basin"] = basin
            df_long["Scenario"] = scenario

            # All non-id columns are treated as constituent columns
            id_vars = ["Scenario", "Region", "Basin", "FU"]
            value_vars = [c for c in df_long.columns if c not in id_vars]

            df_long = df_long.melt(
                id_vars=id_vars,
                value_vars=value_vars,
                var_name="Constituent",
                value_name=value_column,
            )

            rows.append(df_long)

    if not rows:
        return pd.DataFrame(
            columns=[
                "Scenario",
                "Region",
                "Basin",
                "FU",
                "Constituent",
                value_column,
            ]
        )

    return pd.concat(rows, ignore_index=True)


def build_basin_export_summaries(
    cfg: GBRConfig,
    basin_scale: str = "48",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    reporting_units: str = "raw",
) -> pd.DataFrame:
    """
    Build basin-level FU summaries across all scenarios.

    Parameters
    ----------
    cfg : GBRConfig
        Central configuration object.
    basin_scale : str, default "48"
        Basin aggregation scale.
    region : str, optional
        Single region to process.
    regions : list[str], optional
        Multiple regions to process.
    constituents : list[str], optional
        Constituents to include.
    value_column : str, default "LoadToRegExport (kg)"
        Output value column name.

    Returns
    -------
    pd.DataFrame
        Long-format basin FU summaries across all scenarios.
    """
    all_models: list[pd.DataFrame] = []

    for model in cfg.models:
        basin_summaries_by_region, _, _ = build_fu_export_summaries(
            cfg=cfg,
            model=model,
            region=region,
            regions=regions,
            constituents=constituents,
            value_column=value_column,
            units="kg",
            basin_scale=basin_scale,
        )

        df_model = _stack_basin_summaries(
            basin_summaries_by_region=basin_summaries_by_region,
            scenario=model,
            value_column=value_column,
        )
        all_models.append(df_model)

    if not all_models:
        raise ValueError("No basin summaries were generated.")

    basin_df = pd.concat(all_models, ignore_index=True)
    basin_df["BasinScale"] = resolve_basin_column(basin_scale)

    if reporting_units == "report_card":
        basin_df = _convert_report_card_units(
            basin_df,
            value_column=value_column,
            model_years=cfg.model_years,
        )
    elif reporting_units == "raw":
        basin_df = _add_raw_units(
            basin_df,
            value_column=value_column,
        )
    else:
        raise ValueError(
            "Invalid reporting_units. Use 'raw' or 'report_card'."
        )

    return basin_df



def build_basin_scenario_comparison(
    cfg: GBRConfig,
    basin_scale: str = "48",
    region: str | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    reporting_units: str = "raw",
) -> dict[str, pd.DataFrame]:
    """
    Build basin-level scenario comparison tables.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys:
            basin_loads
            compare_ready
            base_wide
            predev_wide
            change_wide
            anthropogenic
            reduction
            percent_reduction
    """
    basin_df = build_basin_export_summaries(
        cfg=cfg,
        basin_scale=basin_scale,
        region=region,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        reporting_units=reporting_units,
    )

    compare_ready = (
        basin_df.groupby(
            ["Scenario", "Region", "Basin", "Constituent", "BasinScale", "Units"],
            as_index=False,
        )[value_column]
        .sum()
    )

    def _scenario_wide(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
        out = df.loc[df["Scenario"] == scenario].copy()

        out = out.drop(columns=["Scenario", "Units"])

        out = out.pivot_table(
            index=["Region", "Basin", "BasinScale"],
            columns="Constituent",
            values=value_column,
            aggfunc="sum",
            fill_value=0,
        )

        out = out.sort_index(axis=0).sort_index(axis=1)
        return out

    base_wide = _scenario_wide(compare_ready, "BASE")
    predev_wide = _scenario_wide(compare_ready, "PREDEV")
    change_wide = _scenario_wide(compare_ready, "CHANGE")

    full_index = base_wide.index.union(predev_wide.index).union(change_wide.index)
    full_columns = base_wide.columns.union(predev_wide.columns).union(change_wide.columns)

    base_wide = base_wide.reindex(index=full_index, columns=full_columns, fill_value=0)
    predev_wide = predev_wide.reindex(index=full_index, columns=full_columns, fill_value=0)
    change_wide = change_wide.reindex(index=full_index, columns=full_columns, fill_value=0)

    anthropogenic = calc_anthropogenic(base_wide, predev_wide)
    reduction = calc_reduction(base_wide, change_wide)
    percent_reduction = calc_percent_reduction(base_wide, predev_wide, change_wide)

    return {
        "basin_loads": basin_df,
        "compare_ready": compare_ready,
        "base_wide": base_wide,
        "predev_wide": predev_wide,
        "change_wide": change_wide,
        "anthropogenic": anthropogenic,
        "reduction": reduction,
        "percent_reduction": percent_reduction,
    }