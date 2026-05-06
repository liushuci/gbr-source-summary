"""
Aggregation-scale summary workflows for gbr_source_summary.

Build scenario-wise grouped FU summaries using the existing FU workflow.

Supported aggregation scales:
- Basin_35
- Manag_Unit_48
- WQI
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


def _add_raw_units(
    df: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    """
    Add raw load units to long-format grouped table.
    """
    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)
    out["Units"] = "kg"
    return out


def _report_unit_for_constituent(constituent: str | None) -> str:
    """
    Return the report-card unit for a constituent.
    """
    key = str(constituent).strip().upper() if constituent is not None else ""
    if key in {"FS", "CS"}:
        return "kt/yr"
    return "t/yr"


def _convert_basin_report_units(
    df: pd.DataFrame,
    *,
    value_column: str,
    model_years: float,
) -> pd.DataFrame:
    """
    Convert basin long-format grouped load table from total kg over model period
    to report-card annual units.

    Expected columns
    ----------------
    - Constituent
    - value_column

    Conversion
    ----------
    - FS, CS -> kt/yr
    - all others -> t/yr
    """
    required = ["Constituent", value_column]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(
            f"Missing required columns for basin report-unit conversion: {missing}"
        )

    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)

    mask_fs = out["Constituent"].isin(["FS", "CS"])

    out.loc[mask_fs, value_column] = out.loc[mask_fs, value_column] / 1e6 / model_years
    out.loc[~mask_fs, value_column] = out.loc[~mask_fs, value_column] / 1e3 / model_years

    out["Units"] = out["Constituent"].apply(_report_unit_for_constituent)

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

    out[value_name] = pd.to_numeric(out[value_name], errors="coerce").fillna(0.0)

    if value_name == "PercentReduction":
        out["Units"] = "%"
        return out

    if reporting_units == "report_card":
        mask_fs = out["Constituent"].isin(["FS", "CS"])
        out.loc[mask_fs, value_name] = out.loc[mask_fs, value_name] / 1e6 / model_years
        out.loc[~mask_fs, value_name] = out.loc[~mask_fs, value_name] / 1e3 / model_years
        out["Units"] = out["Constituent"].apply(_report_unit_for_constituent)
    else:
        out["Units"] = "kg"

    return out


def _stack_basin_summaries(
    basin_summaries_by_region: Dict[str, dict[str, pd.DataFrame]],
    scenario: str,
    value_column: str,
) -> pd.DataFrame:
    """
    Convert nested grouped summary dict into one long dataframe.

    Expected structure
    ------------------
    basin_summaries_by_region[region][group_name] = DataFrame

    Each grouped dataframe is expected to be FU x constituent wide format, e.g.:

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

    Notes
    -----
    The column name 'Basin' is retained for backward compatibility, even though
    the actual aggregation scale may be Basin_35, Manag_Unit_48, or WQI.
    """
    rows: list[pd.DataFrame] = []

    for region, basin_dict in basin_summaries_by_region.items():
        for basin, df in basin_dict.items():
            df_long = df.copy()

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

            id_vars = ["Scenario", "Region", "Basin", "FU"]
            value_vars = [c for c in df_long.columns if c not in id_vars]

            df_long = df_long.melt(
                id_vars=id_vars,
                value_vars=value_vars,
                var_name="Constituent",
                value_name=value_column,
            )

            df_long[value_column] = pd.to_numeric(
                df_long[value_column], errors="coerce"
            ).fillna(0.0)

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
    Build aggregation-scale FU summaries across all scenarios.

    Parameters
    ----------
    cfg : GBRConfig
        Central configuration object.
    basin_scale : str, default "48"
        Aggregation scale. Supported values depend on resolve_basin_column()
        and should include Basin_35, Manag_Unit_48, and WQI.
    region : str, optional
        Single region to process.
    regions : list[str], optional
        Multiple regions to process.
    constituents : list[str], optional
        Constituents to include.
    value_column : str, default "LoadToRegExport (kg)"
        Output value column name.
    reporting_units : str, default "raw"
        Either "raw" or "report_card".

    Returns
    -------
    pd.DataFrame
        Long-format grouped FU summaries across all scenarios.

    Notes
    -----
    The output column names 'Basin' and 'BasinScale' are retained for backward
    compatibility. 'Basin' should be interpreted as the selected aggregation
    unit, which may be Basin_35, Manag_Unit_48, or WQI.
    """
    resolved_scale = resolve_basin_column(basin_scale)

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
            basin_scale=resolved_scale,
        )

        df_model = _stack_basin_summaries(
            basin_summaries_by_region=basin_summaries_by_region,
            scenario=model,
            value_column=value_column,
        )
        all_models.append(df_model)

    if not all_models:
        raise ValueError("No grouped summaries were generated.")

    basin_df = pd.concat(all_models, ignore_index=True)
    basin_df["BasinScale"] = resolved_scale

    if reporting_units == "report_card":
        basin_df = _convert_basin_report_units(
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
    Build aggregation-scale scenario comparison tables.

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

    Notes
    -----
    The output still uses the column names 'Basin' and 'BasinScale' for
    compatibility with existing scripts.
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

    group_cols = [
        "Scenario",
        "Region",
        "Basin",
        "Constituent",
        "BasinScale",
    ]
    if "Units" in basin_df.columns:
        group_cols.append("Units")

    compare_ready = (
        basin_df.groupby(group_cols, as_index=False)[value_column]
        .sum()
    )

    def _scenario_wide(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
        out = df.loc[df["Scenario"] == scenario].copy()

        drop_cols = ["Scenario"]
        if "Units" in out.columns:
            drop_cols.append("Units")
        out = out.drop(columns=drop_cols)

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
    full_columns = (
        base_wide.columns
        .union(predev_wide.columns)
        .union(change_wide.columns)
    )

    base_wide = base_wide.reindex(
        index=full_index,
        columns=full_columns,
        fill_value=0,
    )
    predev_wide = predev_wide.reindex(
        index=full_index,
        columns=full_columns,
        fill_value=0,
    )
    change_wide = change_wide.reindex(
        index=full_index,
        columns=full_columns,
        fill_value=0,
    )

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