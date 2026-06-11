"""
Input/output helpers for gbr_source_summary.

This module contains small, focused loader functions for standard Source output
files. These functions hide the folder structure from the rest of the package
so downstream code can simply request data by region and model.

Currently supported Source tables:
- RegionalSourceSinkSummaryTable.csv
- RawResults.csv
- RegContributorDataGrid.csv
"""

from __future__ import annotations

import pandas as pd

from functools import lru_cache

from .config import GBRConfig

from pathlib import Path

from .package_data import package_data_path

def ensure_output_dir(path: str | Path) -> Path:
    """
    Ensure an output directory exists and return it as a Path.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

def load_regional_source_sink_summary(
    cfg: GBRConfig,
    region: str,
    model: str,
) -> pd.DataFrame:
    """
    Load RegionalSourceSinkSummaryTable.csv for a region/model.

    Parameters
    ----------
    cfg : GBRConfig
        Package configuration object.
    region : str
        Region code, e.g. CY.
    model : str
        Model scenario, e.g. BASE.

    Returns
    -------
    pd.DataFrame
        Loaded CSV table.
    """
    file_path = cfg.get_model_output_dir(region, model) / "RegionalSourceSinkSummaryTable.csv"

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    return pd.read_csv(file_path)


def load_raw_results(
    cfg: GBRConfig,
    region: str,
    model: str,
) -> pd.DataFrame:
    """
    Load RawResults.csv for a region/model.
    """
    base_dir = cfg.get_model_output_dir(region, model)

    csv_path = base_dir / "RawResults.csv"
    xlsx_path = base_dir / "RawResults.xlsx"

    if csv_path.exists():
        return pd.read_csv(csv_path)

    if xlsx_path.exists():
        return pd.read_excel(xlsx_path)

    raise FileNotFoundError(
        f"Could not find RawResults.csv or RawResults.xlsx in {base_dir}"
    )

@lru_cache(maxsize=64)
def _cached_reg_contributor_csv(file_path_str: str) -> pd.DataFrame:
    """
    Cached CSV reader for gigantic RegContributorDataGrid files.

    Prevents repeatedly re-reading the same multi-GB CSVs during
    report-card workflows.
    """

    return pd.read_csv(
        file_path_str,
        low_memory=False,
        dtype={
            "Region": "category",
            "Constituent": "category",
            "FU": "category",
        },
    )

def infer_model_years_from_results(
    cfg: GBRConfig,
    region: str,
    model: str,
) -> int:
    """
    Infer model duration from Num_Days in RegContributorDataGrid.csv.
    """

    file_path = (
        cfg.get_model_output_dir(region, model)
        / "RegContributorDataGrid.csv"
    )

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    df = pd.read_csv(
        file_path,
        usecols=["Num_Days"],
        nrows=1,
    )

    num_days = int(df["Num_Days"].iloc[0])

    years = int(round(num_days / 365.25))

    return years

def load_reg_contributor_data_grid(
    cfg: GBRConfig,
    region: str,
    model: str,
) -> pd.DataFrame:
    """
    Load RegContributorDataGrid.csv for a region/model.
    """
    file_path = cfg.get_model_output_dir(region, model) / "RegContributorDataGrid.csv"

    if not file_path.exists():
        raise FileNotFoundError(file_path)
    return _cached_reg_contributor_csv(str(file_path))


def load_source_outputs(
    cfg: GBRConfig,
    region: str,
    model: str,
) -> dict[str, pd.DataFrame]:
    """
    Load all major Source output tables for a region/model.
    """
    return {
        "regional_summary": load_regional_source_sink_summary(cfg, region, model),
        "raw_results": load_raw_results(cfg, region, model),
        "contributors": load_reg_contributor_data_grid(cfg, region, model),
        "contributors_with_lut": load_reg_contributor_data_grid_with_lut(cfg, region, model),
        "region_lut": load_region_lut(cfg, region),
    }


    

def load_region_lut(
    cfg: GBRConfig,
    region: str,
) -> pd.DataFrame:
    """
    Load packaged region lookup table.

    The LUT is expected at:
    src/gbr_source_summary/data/region_lookup/<REGION>_Subcat_Regions_LUT.csv
    """
    region = str(region).strip().upper()

    file_path = Path(
        package_data_path(
            "region_lookup",
            f"{region}_Subcat_Regions_LUT.csv",
        )
    )

    if not file_path.exists():
        raise FileNotFoundError(
            f"Packaged region LUT not found: {file_path}"
        )

    return pd.read_csv(file_path)

def load_reg_contributor_data_grid_with_lut(
    cfg: GBRConfig,
    region: str,
    model: str,
) -> pd.DataFrame:
    """
    Load RegContributorDataGrid.csv and merge with the region LUT.

    The merge adds columns such as Manag_Unit_48 that are required for
    basin/management-unit summaries.
    """
    contrib = load_reg_contributor_data_grid(cfg, region, model)
    reg_lut = load_region_lut(cfg, region).copy()

    if "SUBCAT" in reg_lut.columns:
        reg_lut = reg_lut.rename(columns={"SUBCAT": "ModelElement"})

    if "ModelElement" not in contrib.columns:
        raise KeyError(
            f"'ModelElement' not found in contributor data. "
            f"Available columns: {contrib.columns.tolist()}"
        )

    if "ModelElement" not in reg_lut.columns:
        raise KeyError(
            f"'ModelElement' not found in region LUT after rename. "
            f"Available columns: {reg_lut.columns.tolist()}"
        )

    merged = pd.merge(contrib, reg_lut, on="ModelElement", how="left")

    return merged

    