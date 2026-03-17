"""
Unit conversion utilities for GBR Source outputs.

Supports both:
- pollutant loads
- flow volumes
"""

from __future__ import annotations

import pandas as pd


NUTRIENT_CONSTITUENTS = {"PN", "PP", "DIN", "DON", "DIP", "DOP"}
SEDIMENT_CONSTITUENTS = {"FS"}
FLOW_CONSTITUENTS = {"Flow"}


def convert_load_units(df: pd.DataFrame, units: str, years: int) -> pd.DataFrame:
    """Convert load tables from kg over model period."""
    if units == "kg":
        return df.copy()
    if units == "t":
        return df / 1000
    if units == "kt":
        return df / 1_000_000
    if units == "t/yr":
        return df / 1000 / years
    if units == "kt/yr":
        return df / 1_000_000 / years

    raise ValueError(f"Unsupported load units: {units}")


def convert_flow_units(df: pd.DataFrame, units: str, years: int) -> pd.DataFrame:
    """
    Convert flow values from Source RegContributorDataGrid.

    In Source outputs, Flow values are stored as kg of water.
    Since density of water ≈ 1 kg/L:

        1 kg ≈ 1 L

    Therefore:

        L  = kg
        ML = kg / 1e6
        GL = kg / 1e9

    Parameters
    ----------
    df : pd.DataFrame
        Flow values stored as kg.
    units : str
        Target units:
            "L"
            "ML"
            "GL"
            "ML/yr"
            "GL/yr"
    years : int
        Simulation period length.

    Returns
    -------
    pd.DataFrame
    """

    if units == "L":
        return df.copy()

    if units == "ML":
        return df / 1000000

    if units == "GL":
        return df / 1000000000

    if units == "ML/yr":
        return df / 1000000 / years

    if units == "GL/yr":
        return df / 1000000000 / years

    raise ValueError(f"Unsupported flow units: {units}")

def convert_report_card_units(
    df: pd.DataFrame,
    value_column: str,
    model_years: float,
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


def apply_units(df: pd.DataFrame, units: str, years: int) -> pd.DataFrame:
    """
    Apply unit conversion.

    Supported:
    - load-only units: kg, t, kt, t/yr, kt/yr
    - flow-only units: ML, GL, ML/yr, GL/yr
    - mixed report-style units: report
    """
    if units == "report":
        return convert_report_units(df, years=years)

    if units in {"kg", "t", "kt", "t/yr", "kt/yr"}:
        return convert_load_units(df, units=units, years=years)

    if units in {"ML", "GL", "ML/yr", "GL/yr"}:
        return convert_flow_units(df, units=units, years=years)

    raise ValueError(f"Unsupported units: {units}")


def label_for_units(units: str) -> str:
    """Return a filename-safe unit label."""
    mapping = {
        "kg": "kg",
        "t": "t",
        "kt": "kt",
        "t/yr": "t_per_yr",
        "kt/yr": "kt_per_yr",
        "ML": "ML",
        "GL": "GL",
        "ML/yr": "ML_per_yr",
        "GL/yr": "GL_per_yr",
        "report": "report_units",
    }
    if units not in mapping:
        raise ValueError(f"Unsupported units: {units}")
    return mapping[units]

def rename_units_column(df: pd.DataFrame, base_name: str, units: str) -> pd.DataFrame:
    """
    Rename dataframe column to reflect output units.

    Example
    -------
    base_name = "LoadToRegExport"
    units = "kt/yr"

    Output column:
    LoadToRegExport (kt/yr)
    """

    if len(df.columns) == 1:
        df = df.copy()
        df.columns = [f"{base_name} ({units})"]

    return df