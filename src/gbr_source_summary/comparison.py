"""
Scenario comparison helpers for gbr_source_summary.

This module contains reusable comparison logic for the standard GBR
model scenarios:
- PREDEV
- BASE
- CHANGE

Typical use cases:
- anthropogenic load = BASE - PREDEV
- reduction = BASE - CHANGE
- percent reduction = (BASE - CHANGE) / (BASE - PREDEV) * 100
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def calc_anthropogenic(base: pd.DataFrame, predev: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate anthropogenic load as BASE - PREDEV.
    """
    return base.subtract(predev, fill_value=0)


def calc_reduction(base: pd.DataFrame, change: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate management reduction as BASE - CHANGE.
    """
    return base.subtract(change, fill_value=0)


def calc_percent_reduction(
    base: pd.DataFrame,
    predev: pd.DataFrame,
    change: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate percent reduction relative to anthropogenic load:

        (BASE - CHANGE) / (BASE - PREDEV) * 100

    Any zero anthropogenic denominator is replaced with NaN before division.
    """
    anthropogenic = calc_anthropogenic(base, predev)
    reduction = calc_reduction(base, change)

    denominator = anthropogenic.replace(0, np.nan)
    percent = reduction.divide(denominator) * 100

    return percent