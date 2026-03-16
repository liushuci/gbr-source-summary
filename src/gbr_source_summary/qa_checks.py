"""
QA checks for gbr_source_summary.

These helpers perform simple consistency checks on summary tables.
Useful for validating RC builds and exported reporting tables.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def check_no_negative_values(df: pd.DataFrame, tol: float = 0.0) -> pd.DataFrame:
    """
    Return rows containing values below -tol.
    """
    df_num = df.apply(pd.to_numeric, errors="coerce")
    mask = (df_num < -tol).any(axis=1)
    return df.loc[mask].copy()


def check_sum_matches_total(
    parts: pd.DataFrame,
    total: pd.Series | pd.DataFrame,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """
    Compare row sums of a table against a total vector.

    Returns a dataframe with:
    - calculated_sum
    - expected_total
    - difference
    """
    parts_num = parts.apply(pd.to_numeric, errors="coerce").fillna(0)
    calc = parts_num.sum(axis=1)

    if isinstance(total, pd.DataFrame):
        if total.shape[1] != 1:
            raise ValueError("total dataframe must have exactly one column")
        expected = pd.to_numeric(total.iloc[:, 0], errors="coerce")
    else:
        expected = pd.to_numeric(total, errors="coerce")

    out = pd.DataFrame(
        {
            "calculated_sum": calc,
            "expected_total": expected,
        }
    )
    out["difference"] = out["calculated_sum"] - out["expected_total"]
    out["within_tolerance"] = out["difference"].abs() <= tol
    return out


def check_anthropogenic_consistency(
    base: pd.DataFrame,
    predev: pd.DataFrame,
    anthropogenic: pd.DataFrame,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """
    Check whether anthropogenic == base - predev.
    """
    calc = base.subtract(predev, fill_value=0)
    diff = calc.subtract(anthropogenic, fill_value=0)

    out = pd.DataFrame(
        {
            "max_abs_difference": diff.abs().max(axis=1),
        }
    )
    out["within_tolerance"] = out["max_abs_difference"] <= tol
    return out


def check_reduction_consistency(
    base: pd.DataFrame,
    change: pd.DataFrame,
    reduction: pd.DataFrame,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """
    Check whether reduction == base - change.
    """
    calc = base.subtract(change, fill_value=0)
    diff = calc.subtract(reduction, fill_value=0)

    out = pd.DataFrame(
        {
            "max_abs_difference": diff.abs().max(axis=1),
        }
    )
    out["within_tolerance"] = out["max_abs_difference"] <= tol
    return out


def check_percent_reduction_bounds(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return rows where percent reduction contains values outside a reasonable range.

    Flags values < -100 or > 100.
    """
    df_num = df.apply(pd.to_numeric, errors="coerce")
    mask = ((df_num < -100) | (df_num > 100)).any(axis=1)
    return df.loc[mask].copy()