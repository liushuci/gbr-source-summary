"""
Naming standardisation helpers for gbr_source_summary.

This module centralises:
- constituent name standardisation
- management unit / basin display name standardisation

The main goal is to avoid hard-coded replacements scattered across notebooks
and scripts.
"""

from __future__ import annotations

import pandas as pd


# Mapping from raw Source constituent names to package-standard names.
CONSTITUENT_MAP = {
    "Sediment - Fine": "FS",
    "Sediment - Coarse": "CS",
    "N_Particulate": "PN",
    "P_Particulate": "PP",
    "P_FRP": "DIP",
    "N_DON": "DON",
    "P_DOP": "DOP",
    "N_DIN": "DIN",
}


# Mapping from raw management unit / basin labels to cleaner display labels.
GBR_NAME_MAP = {
    "Olive-Pascoe": "Olive Pascoe",
    "Jacky Jacky Creek": "Jacky Jacky",
    "Jeannie River": "Jeannie",
    "Endeavour River": "Endeavour",
    "Normanby River": "Normanby",
    "Lockhart River": "Lockhart",
    "Stewart River": "Stewart",
    "Don River": "Don",
    "PlaneC": "Plane",
    "Prossie": "Proserpine",
    "OConnel": "O-Connell",
    "Waterpark": "Water Park",
}


def standardise_constituent_names(values) -> pd.Series:
    """
    Apply standard constituent name mapping to a sequence of values.
    """
    return pd.Series(values).replace(CONSTITUENT_MAP)


def standardise_management_unit_names(values) -> pd.Series:
    """
    Apply standard management unit / basin name mapping to a sequence of values.
    """
    return pd.Series(values).replace(GBR_NAME_MAP)


def apply_constituent_name_standardisation(
    df: pd.DataFrame,
    column: str = "Constituent",
) -> pd.DataFrame:
    """
    Return a copy of a dataframe with standardised constituent names.
    """
    out = df.copy()
    if column in out.columns:
        out[column] = standardise_constituent_names(out[column])
    return out


def apply_management_unit_standardisation(
    df: pd.DataFrame,
    column: str,
) -> pd.DataFrame:
    """
    Return a copy of a dataframe with standardised management unit names.
    """
    out = df.copy()
    if column in out.columns:
        out[column] = standardise_management_unit_names(out[column])
    return out