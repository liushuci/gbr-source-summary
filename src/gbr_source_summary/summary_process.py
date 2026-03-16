"""
Process-based summary builders for gbr_source_summary.

This module converts Source contribution tables into:
- basin-level process summary tables
- region-level process summary tables
- GBR-wide process summary tables

The logic follows the GBR reporting conventions used in the existing notebook.

Supported summary styles
------------------------
Sediment-style constituents:
- FS
- PN
- PP

These are summarised into:
- Hillslope
- Streambank
- Gully
- ChannelRemobilisation

DIN-style constituent:
- DIN

This is summarised into:
- SurfaceRunoff
- Seepage
- PointSource
"""

from __future__ import annotations

import pandas as pd


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    """
    Return a numeric column if present, otherwise a zero-filled series.

    Parameters
    ----------
    df : pd.DataFrame
        Input dataframe.
    col : str
        Column name to retrieve.

    Returns
    -------
    pd.Series
        Numeric series aligned to df.index.
    """
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0)

    return pd.Series(0, index=df.index, dtype=float)


def _reshape_process_series(series: pd.Series, value_column: str) -> pd.DataFrame:
    """
    Convert a grouped process series into a single-row dataframe.

    Example
    -------
    Input series index:
        Hillslope surface soil
        Streambank
        Gully

    Output dataframe columns:
        Hillslope surface soil, Streambank, Gully

    Returns
    -------
    pd.DataFrame
        One-row dataframe for easier process recombination.
    """
    out = pd.DataFrame(series).T
    out.columns.name = None
    out.index = [value_column]
    out = out.apply(pd.to_numeric, errors="coerce").fillna(0)
    return out


def _build_sediment_process_table(
    df_row: pd.DataFrame,
    constituent: str,
    value_column: str,
) -> pd.DataFrame:
    """
    Build the standard sediment-style process table for FS / PN / PP.

    FS uses:
    - Hillslope surface soil
    - Undefined

    PN/PP use:
    - Hillslope no source distinction
    - Undefined

    Returns
    -------
    pd.DataFrame
        Index = reporting process names
        Column = value_column
    """
    out = df_row.copy()

    if constituent == "FS":
        out["Hillslope"] = _safe_col(out, "Hillslope surface soil") + _safe_col(out, "Undefined")
    else:
        out["Hillslope"] = _safe_col(out, "Hillslope no source distinction") + _safe_col(out, "Undefined")

    out["Streambank"] = _safe_col(out, "Streambank")
    out["Gully"] = _safe_col(out, "Gully")
    out["ChannelRemobilisation"] = _safe_col(out, "Channel Remobilisation")

    result = out[["Hillslope", "Streambank", "Gully", "ChannelRemobilisation"]].T
    result.columns = [value_column]
    return result


def _build_din_process_table(
    df_row: pd.DataFrame,
    value_column: str,
) -> pd.DataFrame:
    """
    Build the standard DIN process table.

    DIN uses:
    - Undefined
    - Diffuse Dissolved
    - Hillslope no source distinction
    - Seepage
    - Point Source

    Returns
    -------
    pd.DataFrame
        Index = reporting process names
        Column = value_column
    """
    out = df_row.copy()

    out["SurfaceRunoff"] = (
        _safe_col(out, "Undefined")
        + _safe_col(out, "Diffuse Dissolved")
        + _safe_col(out, "Hillslope no source distinction")
    )
    out["Seepage"] = _safe_col(out, "Seepage")
    out["PointSource"] = _safe_col(out, "Point Source")

    result = out[["SurfaceRunoff", "Seepage", "PointSource"]].T
    result.columns = [value_column]
    return result


def build_basin_process_summary(
    df: pd.DataFrame,
    constituents: list[str],
    value_column: str,
    basin_column: str = "Manag_Unit_48",
    constituent_column: str = "Constituent",
    process_column: str = "Process",
) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Build per-basin process summary tables.

    Parameters
    ----------
    df : pd.DataFrame
        Source contribution dataframe, already merged with LUT if needed.
    constituents : list[str]
        Constituents to summarise, typically ["FS", "PN", "PP", "DIN"].
    value_column : str
        Numeric column to summarise, e.g. "LoadToRegExport (kg)".
    basin_column : str
        Basin / management unit grouping column.
    constituent_column : str
        Constituent column name.
    process_column : str
        Process column name.

    Returns
    -------
    dict[str, dict[str, pd.DataFrame]]
        {
            basin_name: {
                constituent: dataframe indexed by reporting process
            }
        }
    """
    required_cols = [basin_column, constituent_column, process_column, value_column]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise KeyError(
            f"Missing required columns: {missing}. "
            f"Available columns are: {df.columns.tolist()}"
        )

    grouped = (
        df.groupby([basin_column, constituent_column, process_column], dropna=False)
        .sum(numeric_only=True)
    )

    basins = grouped.index.get_level_values(0).unique().tolist()
    result: dict[str, dict[str, pd.DataFrame]] = {}

    for basin in basins:
        basin_group = grouped.loc[basin]
        result[basin] = {}

        available_constituents = basin_group.index.get_level_values(0).unique().tolist()

        for constituent in constituents:
            if constituent not in available_constituents:
                continue

            series = basin_group.loc[constituent][value_column]
            df_row = _reshape_process_series(series, value_column=value_column)

            if constituent in ["FS", "PN", "PP"]:
                result[basin][constituent] = _build_sediment_process_table(
                    df_row=df_row,
                    constituent=constituent,
                    value_column=value_column,
                )
            elif constituent == "DIN":
                result[basin][constituent] = _build_din_process_table(
                    df_row=df_row,
                    value_column=value_column,
                )

    return result


def aggregate_region_process_summary(
    basin_summary: dict[str, dict[str, pd.DataFrame]],
    constituents: list[str],
) -> dict[str, pd.DataFrame]:
    """
    Aggregate basin process summary tables into one regional summary per constituent.

    Parameters
    ----------
    basin_summary : dict
        Basin-level process summaries.
    constituents : list[str]
        Constituents to aggregate.

    Returns
    -------
    dict[str, pd.DataFrame]
        Constituent -> region-level process summary dataframe
    """
    result: dict[str, pd.DataFrame] = {}

    for constituent in constituents:
        total = None

        for basin in basin_summary:
            if constituent not in basin_summary[basin]:
                continue

            df_const = basin_summary[basin][constituent].apply(pd.to_numeric, errors="coerce").fillna(0)
            total = df_const.copy() if total is None else total.add(df_const, fill_value=0)

        result[constituent] = pd.DataFrame() if total is None else total

    return result


def aggregate_gbr_process_summary(
    region_summaries: dict[str, dict[str, pd.DataFrame]],
    constituents: list[str],
) -> dict[str, pd.DataFrame]:
    """
    Aggregate region process summary tables into one GBR-wide summary per constituent.

    Parameters
    ----------
    region_summaries : dict
        Region-level process summaries.
    constituents : list[str]
        Constituents to aggregate.

    Returns
    -------
    dict[str, pd.DataFrame]
        Constituent -> GBR-wide process summary dataframe
    """
    result: dict[str, pd.DataFrame] = {}

    for constituent in constituents:
        total = None

        for region in region_summaries:
            df_const = region_summaries[region].get(constituent, pd.DataFrame())
            if df_const.empty:
                continue

            df_num = df_const.apply(pd.to_numeric, errors="coerce").fillna(0)
            total = df_num.copy() if total is None else total.add(df_num, fill_value=0)

        result[constituent] = pd.DataFrame() if total is None else total

    return result