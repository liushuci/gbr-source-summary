"""
FU-based summary builders for gbr_source_summary.

This module converts Source contribution tables into:
- basin-level FU summary tables
- region-level FU summary tables
- GBR-wide FU summary tables

Typical use case:
- input: RegContributorDataGrid with standardised constituent names
- output: FU x constituent tables for reporting and plotting
"""

from __future__ import annotations

import pandas as pd


def _ensure_fu_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add or combine required FU columns to match reporting structure.

    Current transformations:
    - Dryland Cropping + Irrigated Cropping -> Cropping
    - Urban + Other -> combined column
    - Ensure Bananas, Dairy, Sugarcane exist
    """
    out = df.copy()

    if "Dryland Cropping" in out.columns or "Irrigated Cropping" in out.columns:
        dry = out["Dryland Cropping"] if "Dryland Cropping" in out.columns else 0
        irr = out["Irrigated Cropping"] if "Irrigated Cropping" in out.columns else 0
        out["Cropping"] = pd.to_numeric(dry, errors="coerce").fillna(0) + pd.to_numeric(irr, errors="coerce").fillna(0)

    if "Urban" in out.columns or "Other" in out.columns:
        urban = out["Urban"] if "Urban" in out.columns else 0
        other = out["Other"] if "Other" in out.columns else 0
        out["Urban + Other"] = pd.to_numeric(urban, errors="coerce").fillna(0) + pd.to_numeric(other, errors="coerce").fillna(0)

    for col in ["Bananas", "Dairy", "Sugarcane"]:
        if col not in out.columns:
            out[col] = pd.NA

    return out


def build_basin_fu_summary(
    df: pd.DataFrame,
    constituents: list[str],
    fus_of_interest: list[str],
    value_column: str,
    basin_column: str = "Manag_Unit_48",
    constituent_column: str = "Constituent",
    fu_column: str = "FU",
) -> dict[str, pd.DataFrame]:
    """
    Build per-basin FU summary tables.

    Parameters
    ----------
    df : pd.DataFrame
        Source contribution dataframe.
    constituents : list[str]
        Constituents to include.
    fus_of_interest : list[str]
        Standard FU reporting order.
    value_column : str
        Numeric column to summarise, e.g. 'LoadToRegExport (kg)'.
    basin_column : str
        Basin / management unit column name.
    constituent_column : str
        Constituent column name.
    fu_column : str
        Functional unit column name.

    Returns
    -------
    dict[str, pd.DataFrame]
        Basin name -> dataframe with:
        index = FU
        columns = constituents
    """
    grouped = (
        df.groupby([basin_column, constituent_column, fu_column], dropna=False)
        .sum(numeric_only=True)
    )

    basins = grouped.index.get_level_values(0).unique().tolist()
    result: dict[str, pd.DataFrame] = {}

    for basin in basins:
        basin_group = grouped.loc[basin]
        basin_dict: dict[str, pd.Series] = {}

        for constituent in constituents:
            if constituent not in basin_group.index.get_level_values(0):
                continue
            basin_dict[constituent] = basin_group.loc[constituent][value_column]

        # If the basin has no requested data, return an empty table with expected shape.
        if not basin_dict:
            result[basin] = pd.DataFrame(index=fus_of_interest, columns=constituents)
            continue

        basin_df = pd.DataFrame(basin_dict).T
        basin_df = _ensure_fu_columns(basin_df)

        # Ensure all requested FU columns exist before subsetting.
        for fu in fus_of_interest:
            if fu not in basin_df.columns:
                basin_df[fu] = pd.NA

        basin_df = basin_df[fus_of_interest].T
        result[basin] = basin_df

    return result


def aggregate_region_fu_summary(
    basin_summary: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """
    Aggregate all basin FU summary tables into one regional FU summary.
    """
    total = None

    for _, df in basin_summary.items():
        df_num = df.apply(pd.to_numeric, errors="coerce").fillna(0)
        total = df_num.copy() if total is None else total.add(df_num, fill_value=0)

    return pd.DataFrame() if total is None else total


def aggregate_gbr_fu_summary(
    region_summaries: dict[str, pd.DataFrame]
) -> pd.DataFrame:
    """
    Aggregate all regional FU summary tables into one GBR-wide FU summary.
    """
    total = None

    for _, df in region_summaries.items():
        df_num = df.apply(pd.to_numeric, errors="coerce").fillna(0)
        total = df_num.copy() if total is None else total.add(df_num, fill_value=0)

    return pd.DataFrame() if total is None else total