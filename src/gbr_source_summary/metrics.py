"""
Model evaluation metrics for gbr_source_summary.

This module provides reusable statistical metrics used in GBR model evaluation,
especially for Moriasi-style comparisons between monitored and modelled values.

Implemented metrics:
- R²
- NSE
- PBIAS
- RSR

All functions first coerce input to numeric values and remove missing pairs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _clean_pair(observed, modelled) -> pd.DataFrame:
    """
    Convert observed/modelled inputs to numeric series and drop missing pairs.

    Returns
    -------
    pd.DataFrame
        Two-column dataframe with columns:
        - observed
        - modelled
    """
    df = pd.DataFrame(
        {
            "observed": pd.to_numeric(pd.Series(observed), errors="coerce"),
            "modelled": pd.to_numeric(pd.Series(modelled), errors="coerce"),
        }
    ).dropna()

    return df


def calc_r2(observed, modelled) -> float:
    """
    Calculate R² as squared Pearson correlation.

    Returns np.nan if fewer than two valid pairs are available.
    """
    df = _clean_pair(observed, modelled)
    if len(df) < 2:
        return np.nan

    corr = df["observed"].corr(df["modelled"])
    if pd.isna(corr):
        return np.nan

    return float(round(corr**2, 2))


def calc_nse(observed, modelled) -> float:
    """
    Calculate Nash-Sutcliffe Efficiency (NSE).

    Returns np.nan if fewer than two valid pairs are available or if the
    observed series has zero variance.
    """
    df = _clean_pair(observed, modelled)
    if len(df) < 2:
        return np.nan

    obs = df["observed"]
    sim = df["modelled"]

    denominator = ((obs - obs.mean()) ** 2).sum()
    if denominator == 0:
        return np.nan

    numerator = ((obs - sim) ** 2).sum()
    return float(round(1 - numerator / denominator, 2))


def calc_pbias(observed, modelled) -> float:
    """
    Calculate percent bias (PBIAS).

    Positive values indicate underestimation by the model on average.
    Negative values indicate overestimation.

    Returns np.nan if the observed sum is zero.
    """
    df = _clean_pair(observed, modelled)
    if len(df) == 0:
        return np.nan

    obs = df["observed"]
    sim = df["modelled"]

    denominator = obs.sum()
    if denominator == 0:
        return np.nan

    value = 100 * ((obs - sim).sum() / denominator)
    return float(round(value, 2))


def calc_rsr(observed, modelled) -> float:
    """
    Calculate RSR (RMSE-observations standard deviation ratio).

    Returns np.nan if fewer than two valid pairs are available or if the
    observed standard deviation is zero.
    """
    df = _clean_pair(observed, modelled)
    if len(df) < 2:
        return np.nan

    obs = df["observed"]
    sim = df["modelled"]

    rmse = np.sqrt(((obs - sim) ** 2).mean())
    obs_std = obs.std(ddof=1)

    if pd.isna(obs_std) or obs_std == 0:
        return np.nan

    return float(round(rmse / obs_std, 2))