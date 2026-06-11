from __future__ import annotations

import numpy as np
import pandas as pd


def _to_1d_numeric_array(x) -> np.ndarray:
    arr = np.asarray(x, dtype=object)

    if arr.ndim > 1:
        arr = arr.reshape(-1)

    s = pd.to_numeric(pd.Series(arr), errors="coerce")
    return s.to_numpy(dtype=float)


def _clean_pair(observed, modelled) -> pd.DataFrame:
    obs = _to_1d_numeric_array(observed)
    sim = _to_1d_numeric_array(modelled)

    n = min(len(obs), len(sim))

    df = pd.DataFrame(
        {
            "observed": obs[:n],
            "modelled": sim[:n],
        }
    ).dropna()

    return df


def calc_r2(observed, modelled) -> float:
    df = _clean_pair(observed, modelled)
    if len(df) < 2:
        return np.nan

    corr = df["observed"].corr(df["modelled"])
    if pd.isna(corr):
        return np.nan

    return float(round(float(corr) ** 2, 2))


def calc_nse(observed, modelled) -> float:
    df = _clean_pair(observed, modelled)
    if len(df) < 2:
        return np.nan

    obs = df["observed"].to_numpy(dtype=float)
    sim = df["modelled"].to_numpy(dtype=float)

    denominator = np.sum((obs - np.mean(obs)) ** 2)
    if denominator == 0:
        return np.nan

    numerator = np.sum((obs - sim) ** 2)
    value = 1 - numerator / denominator

    return float(round(float(value), 2))


def calc_pbias(observed, modelled) -> float:
    """
    Moriasi convention:
    Positive PBIAS = model overestimation.
    Negative PBIAS = model underestimation.
    """
    df = _clean_pair(observed, modelled)
    if len(df) == 0:
        return np.nan

    obs = df["observed"].to_numpy(dtype=float)
    sim = df["modelled"].to_numpy(dtype=float)

    denominator = np.sum(obs)
    if denominator == 0:
        return np.nan

    value = 100.0 * np.sum(sim - obs) / denominator

    return float(round(float(value), 2))


def calc_rsr(observed, modelled) -> float:
    df = _clean_pair(observed, modelled)
    if len(df) < 2:
        return np.nan

    obs = df["observed"].to_numpy(dtype=float)
    sim = df["modelled"].to_numpy(dtype=float)

    rmse = np.sqrt(np.mean((obs - sim) ** 2))
    obs_std = np.std(obs, ddof=1)

    if pd.isna(obs_std) or obs_std == 0:
        return np.nan

    value = rmse / obs_std

    return float(round(float(value), 2))