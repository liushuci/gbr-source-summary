"""
Flow summary builders for gbr_source_summary.

This module handles flow summaries separately from pollutant load summaries.

Typical use cases:
- summarise annual or total flow by region
- aggregate site or basin flow tables
- prepare flow outputs for comparison against monitored data

Design note
-----------
Flow is treated separately because it is a volume metric rather than a load.
"""

from __future__ import annotations

import pandas as pd


def build_group_flow_summary(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    flow_column: str = "Constituent",
    flow_value: str = "Flow",
) -> pd.DataFrame:
    """
    Build a flow summary by grouping column.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe containing flow rows.
    group_column : str
        Column used for grouping, e.g. 'Manag_Unit_48', 'FU', or 'Site'.
    value_column : str
        Numeric flow value column.
    flow_column : str
        Column that identifies the constituent/variable type.
    flow_value : str
        Value in flow_column representing flow.

    Returns
    -------
    pd.DataFrame
        Dataframe indexed by group_column with one column equal to value_column.
    """
    required_cols = [group_column, value_column, flow_column]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise KeyError(
            f"Missing required columns: {missing}. "
            f"Available columns are: {df.columns.tolist()}"
        )

    flow_df = df[df[flow_column] == flow_value].copy()
    if flow_df.empty:
        return pd.DataFrame(columns=[value_column])

    summary = (
        flow_df.groupby(group_column, dropna=False)[value_column]
        .sum()
        .to_frame()
    )

    return summary


def aggregate_flow_tables(
    tables: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """
    Aggregate multiple flow tables into one combined table.

    Parameters
    ----------
    tables : dict[str, pd.DataFrame]
        Mapping of name -> flow dataframe.

    Returns
    -------
    pd.DataFrame
        Combined flow dataframe.
    """
    total = None

    for _, df in tables.items():
        df_num = df.apply(pd.to_numeric, errors="coerce").fillna(0)
        total = df_num.copy() if total is None else total.add(df_num, fill_value=0)

    return pd.DataFrame() if total is None else total


def build_fu_flow_summary(
    df: pd.DataFrame,
    value_column: str,
    fu_column: str = "FU",
    flow_column: str = "Constituent",
    flow_value: str = "Flow",
) -> pd.DataFrame:
    """
    Build a flow summary by functional unit.

    Returns
    -------
    pd.DataFrame
        Index = FU, column = value_column
    """
    return build_group_flow_summary(
        df=df,
        group_column=fu_column,
        value_column=value_column,
        flow_column=flow_column,
        flow_value=flow_value,
    )


def build_basin_flow_summary(
    df: pd.DataFrame,
    value_column: str,
    basin_column: str = "Manag_Unit_48",
    flow_column: str = "Constituent",
    flow_value: str = "Flow",
) -> pd.DataFrame:
    """
    Build a flow summary by basin / management unit.

    Returns
    -------
    pd.DataFrame
        Index = basin, column = value_column
    """
    return build_group_flow_summary(
        df=df,
        group_column=basin_column,
        value_column=value_column,
        flow_column=flow_column,
        flow_value=flow_value,
    )