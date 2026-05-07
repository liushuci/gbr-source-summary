"""
Land-use and rainfall summary workflows for gbr_source_summary.

This module supports:
- legacy-style region FU area + stream length summary
- detailed land-use area summaries by subcatchment, MU48 and region
- rainfall summaries by subcatchment, Basin_35, MU48, region and GBR
- bundle-compatible runner: run_landuse_rainfall_summary()

Main input files per region/model:
- fuAreasTable.csv
- climateTable.csv
- ParameterTable.csv
- <REGION>_Subcat_Regions_LUT.csv
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import GBRConfig
from .export import ensure_output_dir
from .export_excel import export_tables_to_excel


# =========================================================
# Defaults / constants
# =========================================================

DEFAULT_MODEL = "BASE"
DEFAULT_RC = "Gold_93_23"

DEFAULT_FU_ORDER = [
    "Bananas",
    "Conservation",
    "Cropping",
    "Dairy",
    "Forestry",
    "Grazing",
    "Horticulture",
    "Sugarcane",
    "Urban + Other",
]

FU_LOAD_ORDER = [
    "Bananas",
    "Conservation",
    "Cropping",
    "Dairy",
    "Forestry",
    "Grazing",
    "Horticulture",
    "Stream",
    "Sugarcane",
    "Urban + Other",
]

REGION_NAME_MAP = {
    "CY": "Cape York",
    "WT": "Wet Tropics",
    "BU": "Burdekin",
    "MW": "Mackay Whitsunday",
    "FI": "Fitzroy",
    "BM": "Burnett Mary",
}

M2_TO_HA = 1.0 / 10000.0
M_TO_KM = 1.0 / 1000.0

KT_CONSTITUENTS = ["FS"]


# =========================================================
# Generic helpers
# =========================================================

def find_column(df: pd.DataFrame, candidates: List[str], df_name: str = "dataframe") -> str:
    """
    Find first matching column from a candidate list.
    """
    for col in candidates:
        if col in df.columns:
            return col

    lower_lookup = {str(c).strip().lower(): c for c in df.columns}
    for col in candidates:
        key = str(col).strip().lower()
        if key in lower_lookup:
            return lower_lookup[key]

    raise KeyError(
        f"None of these columns were found in {df_name}: {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def _ensure_columns(df: pd.DataFrame, required: List[str], df_name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"{df_name} missing required columns: {missing}")


def _check_duplicates(df: pd.DataFrame, subset_cols: List[str]) -> pd.DataFrame:
    dup_mask = df.duplicated(subset=subset_cols, keep=False)
    return df.loc[dup_mask].copy()


def _check_rainfall_consistency(df: pd.DataFrame) -> pd.DataFrame:
    tmp = df[df["Area_m2"] > 0].copy()
    chk = (
        tmp.groupby("ModelElement")["Rainfall_mm_total"]
        .nunique(dropna=True)
        .reset_index(name="n_unique_rain")
    )
    return chk[chk["n_unique_rain"] > 1].copy()


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce")
    den = pd.to_numeric(denominator, errors="coerce")
    out = num / den.where(den != 0)
    return out.fillna(0.0)


def _normalise_id(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip()


def _selected_regions(cfg: GBRConfig, regions: list[str] | None = None) -> list[str]:
    if regions is not None:
        return regions

    cfg_regions = getattr(cfg, "regions", None)
    if cfg_regions:
        return list(cfg_regions)

    return ["CY", "WT", "BU", "MW", "FI", "BM"]


def _cfg_main_path(cfg: GBRConfig) -> Path:
    main_path = getattr(cfg, "main_path", None)
    if main_path is None:
        raise AttributeError("GBRConfig must have main_path.")
    return Path(main_path)


def _cfg_rc(cfg: GBRConfig) -> str:
    for attr in ["rc", "RC", "run_code", "model_run", "model_run_name"]:
        value = getattr(cfg, attr, None)
        if value:
            return str(value)
    return DEFAULT_RC


def _cfg_model_years(cfg: GBRConfig) -> float:
    years = getattr(cfg, "model_years", None)
    if years is None:
        return 30.0
    return float(years)


@lru_cache(maxsize=None)
def _read_csv_cached(path_str: str) -> pd.DataFrame:
    try:
        return pd.read_csv(
            path_str,
            low_memory=False,
            on_bad_lines="skip",
        )
    except Exception as e:
        print(f"⚠ Failed reading CSV: {path_str}")
        print(e)
        raise


    

def _read_csv(path: Path) -> pd.DataFrame:
    return _read_csv_cached(str(path))


# =========================================================
# File discovery
# =========================================================

def _model_output_dir(
    cfg: GBRConfig,
    region: str,
    model: str = DEFAULT_MODEL,
) -> Path:
    main_path = _cfg_main_path(cfg)
    rc = _cfg_rc(cfg)

    candidates = [
        main_path / "Gold_ResultsSets_PointOfTruth" / region / "Model_Outputs" / f"{model}_{rc}",
        main_path / region / "Model_Outputs" / f"{model}_{rc}",
    ]

    for path in candidates:
        if path.exists():
            return path

    search_roots = [
        main_path / "Gold_ResultsSets_PointOfTruth" / region / "Model_Outputs",
        main_path / region / "Model_Outputs",
    ]

    for root in search_roots:
        if root.exists():
            matches = sorted(root.glob(f"{model}_*"))
            if matches:
                return matches[0]

    raise FileNotFoundError(
        f"Could not find model output folder for region={region}, model={model}. "
        f"Tried: {[str(p) for p in candidates]}"
    )


def _find_table_path(
    cfg: GBRConfig,
    region: str,
    filename: str,
    model: str = DEFAULT_MODEL,
) -> Path:
    out_dir = _model_output_dir(cfg, region=region, model=model)
    direct = out_dir / filename

    if direct.exists():
        return direct

    matches = sorted(out_dir.glob(f"**/{filename}"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"Could not find {filename} in {out_dir}")


def _find_region_lut_path(cfg: GBRConfig, region: str) -> Path:
    main_path = _cfg_main_path(cfg)

    candidates = [
        main_path / "Regions" / f"{region}_Subcat_Regions_LUT.csv",
        main_path.parent / "Regions" / f"{region}_Subcat_Regions_LUT.csv",
        main_path / f"{region}_Subcat_Regions_LUT.csv",
    ]

    for path in candidates:
        if path.exists():
            return path

    search_roots = [
        main_path / "Regions",
        main_path.parent / "Regions",
        main_path,
        main_path.parent,
    ]

    for root in search_roots:
        if root.exists():
            matches = sorted(root.glob(f"**/{region}_Subcat_Regions_LUT*.csv"))
            if matches:
                return matches[0]

    raise FileNotFoundError(
        f"Could not find LUT for {region}. Expected file like "
        f"{region}_Subcat_Regions_LUT.csv"
    )


def load_landuse_rainfall_inputs(
    cfg: GBRConfig,
    regions: list[str] | None = None,
    model: str = DEFAULT_MODEL,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    """
    Load fuAreasTable, climateTable, ParameterTable and region LUT tables
    for selected regions.
    """
    selected = _selected_regions(cfg, regions)

    fu_area_tables: dict[str, pd.DataFrame] = {}
    climate_tables: dict[str, pd.DataFrame] = {}
    parameter_tables: dict[str, pd.DataFrame] = {}
    reg_lut_tables: dict[str, pd.DataFrame] = {}

    for region in selected:
        fu_area_tables[region] = _read_csv(
            _find_table_path(cfg, region, "fuAreasTable.csv", model=model)
        )
        climate_tables[region] = _read_csv(
            _find_table_path(cfg, region, "climateTable.csv", model=model)
        )

        try:
            parameter_tables[region] = _read_csv(
                _find_table_path(cfg, region, "ParameterTable.csv", model=model)
            )
        except FileNotFoundError:
            parameter_tables[region] = pd.DataFrame()

        reg_lut_tables[region] = _read_csv(_find_region_lut_path(cfg, region))

    return fu_area_tables, climate_tables, parameter_tables, reg_lut_tables


# =========================================================
# LUT normalisation
# =========================================================

def _normalise_lut(
    reg_lut_raw: pd.DataFrame,
    region: str,
    require_mu48: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Standardise LUT columns to:
    - ModelElement
    - Basin_35
    - Manag_Unit_48 if present
    - Region
    """
    lut_key_col = find_column(
        reg_lut_raw,
        ["ModelElement", "SUBCAT", "Subcat", "subcat", "Reg_SC"],
        "regLUT",
    )
    lut_basin35_col = find_column(
        reg_lut_raw,
        ["Basin_35", "Basin35", "Basin"],
        "regLUT",
    )

    lut_mu48_col = None
    for c in ["Manag_Unit_48", "Manag Unit 48", "Management_Unit_48", "MU_48"]:
        if c in reg_lut_raw.columns:
            lut_mu48_col = c
            break

    if require_mu48 and lut_mu48_col is None:
        raise KeyError(f"No Manag_Unit_48 column found in LUT for {region}")

    reg_lut = reg_lut_raw.rename(
        columns={
            lut_key_col: "ModelElement",
            lut_basin35_col: "Basin_35",
        }
    ).copy()

    if lut_mu48_col is not None:
        reg_lut = reg_lut.rename(columns={lut_mu48_col: "Manag_Unit_48"})

    reg_lut["ModelElement"] = _normalise_id(reg_lut["ModelElement"])
    reg_lut["Region"] = region

    keep_cols = ["ModelElement", "Basin_35", "Region"]
    if "Manag_Unit_48" in reg_lut.columns:
        keep_cols.append("Manag_Unit_48")

    lut_dup_before = _check_duplicates(reg_lut[keep_cols].copy(), ["ModelElement"])
    reg_lut = reg_lut[keep_cols].drop_duplicates(subset=["ModelElement"]).copy()

    return reg_lut, lut_dup_before


# =========================================================
# Legacy-style FU area / stream length summary
# =========================================================

def summarise_region_fu_area(
    fu_area_table: pd.DataFrame,
    fu_order: Optional[List[str]] = None,
    area_col: Optional[str] = None,
    fu_col: str = "FU",
) -> pd.DataFrame:
    if fu_order is None:
        fu_order = DEFAULT_FU_ORDER

    if area_col is None:
        area_col = find_column(fu_area_table, ["Area", "Area_m2", "Area (m2)"], "fu_area_table")

    _ensure_columns(fu_area_table, [fu_col, area_col], "fu_area_table")

    fu_area_summary = fu_area_table.groupby(fu_col).sum(numeric_only=True)

    if area_col not in fu_area_summary.columns:
        raise KeyError(
            f"Area column '{area_col}' not found after groupby. "
            f"Available numeric columns: {list(fu_area_summary.columns)}"
        )

    fu_area = fu_area_summary[[area_col]].T.copy()

    if "Dryland Cropping" in fu_area.columns or "Irrigated Cropping" in fu_area.columns:
        fu_area["Cropping"] = (
            fu_area.get("Dryland Cropping", 0)
            + fu_area.get("Irrigated Cropping", 0)
        )

    fu_area["Urban + Other"] = fu_area.get("Other", 0) + fu_area.get("Urban", 0)

    for fu in ["Bananas", "Dairy", "Sugarcane"]:
        if fu not in fu_area.columns:
            fu_area[fu] = np.nan

    for fu in fu_order:
        if fu not in fu_area.columns:
            fu_area[fu] = np.nan

    fu_area = fu_area[fu_order].T
    fu_area.columns = ["Area_m2"]

    return fu_area


def build_fu_area_summary_across_regions(
    fu_area_tables_by_region: Dict[str, pd.DataFrame],
    region_order: Optional[List[str]] = None,
    region_name_map: Optional[Dict[str, str]] = None,
    fu_order: Optional[List[str]] = None,
) -> pd.DataFrame:
    if region_order is None:
        region_order = list(fu_area_tables_by_region.keys())
    if region_name_map is None:
        region_name_map = REGION_NAME_MAP
    if fu_order is None:
        fu_order = DEFAULT_FU_ORDER

    region_fu_area = {}

    for region in region_order:
        region_fu_area[region] = summarise_region_fu_area(
            fu_area_tables_by_region[region],
            fu_order=fu_order,
        )

    fu_area_summary = pd.DataFrame()

    for region in region_order:
        tmp = region_fu_area[region].T * M2_TO_HA
        tmp.index = [region]
        fu_area_summary = pd.concat([fu_area_summary, tmp], axis=0)

    fu_area_summary.loc["GBR"] = fu_area_summary.fillna(0).sum(axis=0)

    pretty_index = [region_name_map.get(r, r) for r in region_order] + ["GBR"]
    fu_area_summary.index = pretty_index

    return fu_area_summary.fillna(0)


def summarise_region_stream_length(
    parameter_table: pd.DataFrame,
    parameter_col: str = "PARAMETER",
    value_col: str = "VALUE",
    target_parameter: str = "Link Length",
) -> float:
    if parameter_table.empty:
        return 0.0

    _ensure_columns(parameter_table, [parameter_col, value_col], "parameter_table")

    lengths = parameter_table.loc[
        parameter_table[parameter_col].astype(str).str.strip() == target_parameter,
        [value_col],
    ].copy()

    lengths[value_col] = pd.to_numeric(lengths[value_col], errors="coerce")
    total_length_km = lengths[value_col].sum() * M_TO_KM

    return float(total_length_km)


def build_stream_length_summary_across_regions(
    parameter_tables_by_region: Dict[str, pd.DataFrame],
    region_order: Optional[List[str]] = None,
    region_name_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    if region_order is None:
        region_order = list(parameter_tables_by_region.keys())
    if region_name_map is None:
        region_name_map = REGION_NAME_MAP

    rows = []
    for region in region_order:
        rows.append(summarise_region_stream_length(parameter_tables_by_region[region]))

    stream_df = pd.DataFrame({"Stream": rows}, index=region_order)
    stream_df.loc["GBR"] = stream_df["Stream"].sum()

    pretty_index = [region_name_map.get(r, r) for r in region_order] + ["GBR"]
    stream_df.index = pretty_index

    return stream_df.fillna(0)


def build_land_use_stream_summary(
    fu_area_tables_by_region: Dict[str, pd.DataFrame],
    parameter_tables_by_region: Dict[str, pd.DataFrame],
    region_order: Optional[List[str]] = None,
    region_name_map: Optional[Dict[str, str]] = None,
    fu_order: Optional[List[str]] = None,
    round_to_int: bool = True,
) -> pd.DataFrame:
    fu_summary = build_fu_area_summary_across_regions(
        fu_area_tables_by_region=fu_area_tables_by_region,
        region_order=region_order,
        region_name_map=region_name_map,
        fu_order=fu_order,
    )

    stream_summary = build_stream_length_summary_across_regions(
        parameter_tables_by_region=parameter_tables_by_region,
        region_order=region_order,
        region_name_map=region_name_map,
    )

    out = fu_summary.copy()
    insert_loc = min(7, len(out.columns))
    out.insert(loc=insert_loc, column="Stream", value=stream_summary["Stream"])

    rename_map = {
        "Bananas": "Banana (ha)",
        "Conservation": "Conservation (ha)",
        "Cropping": "Cropping (ha)",
        "Dairy": "Dairy (ha)",
        "Forestry": "Forestry (ha)",
        "Grazing": "Grazing (ha)",
        "Horticulture": "Horticulture (ha)",
        "Stream": "Stream (km)",
        "Sugarcane": "Sugarcane (ha)",
        "Urban + Other": "Urban + Other (ha)",
    }
    out = out.rename(columns=rename_map)

    if round_to_int:
        out = out.fillna(0).round(0).astype(int)

    return out


# =========================================================
# Detailed land-use area workflow
# =========================================================

def prepare_region_fu_area_table(
    fu_areas_df_raw: pd.DataFrame,
    reg_lut_raw: pd.DataFrame,
    region: str,
    fus_of_interest: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, float]]:
    reg_lut, lut_dup_before = _normalise_lut(
        reg_lut_raw=reg_lut_raw,
        region=region,
        require_mu48=True,
    )

    fuarea_key_col = find_column(
        fu_areas_df_raw,
        ["Catchment", "ModelElement", "SUBCAT", "Subcat", "Reg_SC"],
        "fuAreas_df",
    )
    fuarea_fu_col = find_column(fu_areas_df_raw, ["FU", "Functional Unit"], "fuAreas_df")
    fuarea_area_col = find_column(fu_areas_df_raw, ["Area", "Area_m2", "Area (m2)"], "fuAreas_df")

    fu_areas_df = fu_areas_df_raw.rename(
        columns={
            fuarea_key_col: "ModelElement",
            fuarea_fu_col: "FU",
            fuarea_area_col: "Area_m2",
        }
    ).copy()

    fu_areas_df = fu_areas_df[["ModelElement", "FU", "Area_m2"]].copy()
    fu_areas_df["ModelElement"] = _normalise_id(fu_areas_df["ModelElement"])
    fu_areas_df["FU"] = fu_areas_df["FU"].astype(str).str.strip()
    fu_areas_df["Area_m2"] = pd.to_numeric(fu_areas_df["Area_m2"], errors="coerce").fillna(0.0)

    if fus_of_interest is not None:
        fu_areas_df = fu_areas_df[fu_areas_df["FU"].isin(fus_of_interest)].copy()

    fuarea_dups = _check_duplicates(fu_areas_df, ["ModelElement", "FU"])

    fu_areas_df = (
        fu_areas_df
        .groupby(["ModelElement", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )

    area_before_lut_merge = float(fu_areas_df["Area_m2"].sum())

    fu_area_df = pd.merge(fu_areas_df, reg_lut, on="ModelElement", how="left")
    area_after_lut_merge = float(fu_area_df["Area_m2"].sum())

    unmatched_lut_df = fu_area_df[fu_area_df["Manag_Unit_48"].isna()].copy()
    fu_area_df = fu_area_df[fu_area_df["Area_m2"] > 0].copy()

    qa_tables = {
        "lut_dup_before": lut_dup_before,
        "fuarea_dups": fuarea_dups,
        "unmatched_lut": unmatched_lut_df,
    }

    qa_metrics = {
        "Area_before_LUT_merge_m2": area_before_lut_merge,
        "Area_after_LUT_merge_m2": area_after_lut_merge,
        "Unmatched_LUT_rows": float(len(unmatched_lut_df)),
    }

    return fu_area_df, qa_tables, qa_metrics


def collapse_region_fu_area_outputs(
    fu_area_df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    subcat_fu_df = (
        fu_area_df
        .groupby(["Region", "ModelElement", "Basin_35", "Manag_Unit_48", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )
    subcat_fu_df["Area_ha"] = subcat_fu_df["Area_m2"] / 1e4
    subcat_fu_df["Area_km2"] = subcat_fu_df["Area_m2"] / 1e6

    subcat_total_area = (
        subcat_fu_df
        .groupby(["Region", "ModelElement"], as_index=False)
        .agg(SubcatTotalArea_m2=("Area_m2", "sum"))
    )
    subcat_fu_df = pd.merge(subcat_fu_df, subcat_total_area, on=["Region", "ModelElement"], how="left")
    subcat_fu_df["Area_pct_of_SUBCAT"] = (
        _safe_divide(subcat_fu_df["Area_m2"], subcat_fu_df["SubcatTotalArea_m2"]) * 100.0
    )

    basin35_fu_df = (
        fu_area_df
        .groupby(["Region", "Basin_35", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )
    basin35_fu_df["Area_ha"] = basin35_fu_df["Area_m2"] / 1e4
    basin35_fu_df["Area_km2"] = basin35_fu_df["Area_m2"] / 1e6

    basin35_total_area = (
        basin35_fu_df
        .groupby(["Region", "Basin_35"], as_index=False)
        .agg(Basin35TotalArea_m2=("Area_m2", "sum"))
    )
    basin35_fu_df = pd.merge(basin35_fu_df, basin35_total_area, on=["Region", "Basin_35"], how="left")
    basin35_fu_df["Area_pct_of_Basin35"] = (
        _safe_divide(basin35_fu_df["Area_m2"], basin35_fu_df["Basin35TotalArea_m2"]) * 100.0
    )

    mu48_fu_df = (
        fu_area_df
        .dropna(subset=["Manag_Unit_48"])
        .groupby(["Region", "Manag_Unit_48", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )
    mu48_fu_df["Area_ha"] = mu48_fu_df["Area_m2"] / 1e4
    mu48_fu_df["Area_km2"] = mu48_fu_df["Area_m2"] / 1e6

    mu48_total_area = (
        mu48_fu_df
        .groupby(["Region", "Manag_Unit_48"], as_index=False)
        .agg(MU48TotalArea_m2=("Area_m2", "sum"))
    )
    mu48_fu_df = pd.merge(mu48_fu_df, mu48_total_area, on=["Region", "Manag_Unit_48"], how="left")
    mu48_fu_df["Area_pct_of_MU48"] = (
        _safe_divide(mu48_fu_df["Area_m2"], mu48_fu_df["MU48TotalArea_m2"]) * 100.0
    )

    region_fu_df = (
        fu_area_df
        .groupby(["Region", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )
    region_fu_df["Area_ha"] = region_fu_df["Area_m2"] / 1e4
    region_fu_df["Area_km2"] = region_fu_df["Area_m2"] / 1e6

    region_total_area = (
        region_fu_df
        .groupby(["Region"], as_index=False)
        .agg(RegionTotalArea_m2=("Area_m2", "sum"))
    )
    region_fu_df = pd.merge(region_fu_df, region_total_area, on="Region", how="left")
    region_fu_df["Area_pct_of_Region"] = (
        _safe_divide(region_fu_df["Area_m2"], region_fu_df["RegionTotalArea_m2"]) * 100.0
    )

    return {
        "fu_area": fu_area_df,
        "subcat_fu": subcat_fu_df,
        "basin35_fu": basin35_fu_df,
        "mu48_fu": mu48_fu_df,
        "region_fu": region_fu_df,
    }


def build_land_use_detailed_summary_across_regions(
    fu_area_tables_by_region: Dict[str, pd.DataFrame],
    reg_lut_tables_by_region: Dict[str, pd.DataFrame],
    region_order: Optional[List[str]] = None,
    fus_of_interest: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    if region_order is None:
        region_order = list(fu_area_tables_by_region.keys())

    fuarea_by_region = {}
    subcat_fu_by_region = {}
    basin35_fu_by_region = {}
    mu48_fu_by_region = {}
    region_fu_by_region = {}

    qa_summary_rows = []

    for region in region_order:
        fu_area_df, qa_tables, qa_metrics = prepare_region_fu_area_table(
            fu_areas_df_raw=fu_area_tables_by_region[region],
            reg_lut_raw=reg_lut_tables_by_region[region],
            region=region,
            fus_of_interest=fus_of_interest,
        )

        collapsed = collapse_region_fu_area_outputs(fu_area_df)

        fuarea_by_region[region] = collapsed["fu_area"]
        subcat_fu_by_region[region] = collapsed["subcat_fu"]
        basin35_fu_by_region[region] = collapsed["basin35_fu"]
        mu48_fu_by_region[region] = collapsed["mu48_fu"]
        region_fu_by_region[region] = collapsed["region_fu"]

        qa_summary_rows.append({
            "Region": region,
            "LUT_dup_ModelElement_before_dedup": len(qa_tables["lut_dup_before"][["ModelElement"]].drop_duplicates()) if not qa_tables["lut_dup_before"].empty else 0,
            "FUArea_dup_ModelElement_FU_keys": len(qa_tables["fuarea_dups"][["ModelElement", "FU"]].drop_duplicates()) if not qa_tables["fuarea_dups"].empty else 0,
            "Area_before_LUT_merge_m2": qa_metrics["Area_before_LUT_merge_m2"],
            "Area_after_LUT_merge_m2": qa_metrics["Area_after_LUT_merge_m2"],
            "Unmatched_LUT_rows": int(qa_metrics["Unmatched_LUT_rows"]),
            "SubcatFU_rows": len(collapsed["subcat_fu"]),
            "Basin35FU_rows": len(collapsed["basin35_fu"]),
            "MU48FU_rows": len(collapsed["mu48_fu"]),
            "RegionFU_rows": len(collapsed["region_fu"]),
        })

    fu_area_all_df = pd.concat([fuarea_by_region[r] for r in region_order], ignore_index=True)
    subcat_fu_all_df = pd.concat([subcat_fu_by_region[r] for r in region_order], ignore_index=True)
    basin35_fu_all_df = pd.concat([basin35_fu_by_region[r] for r in region_order], ignore_index=True)
    mu48_fu_all_df = pd.concat([mu48_fu_by_region[r] for r in region_order], ignore_index=True)
    region_fu_all_df = pd.concat([region_fu_by_region[r] for r in region_order], ignore_index=True)

    basin35_area_wide_df = (
        basin35_fu_all_df
        .pivot_table(index=["Region", "Basin_35"], columns="FU", values="Area_ha", aggfunc="sum", fill_value=0)
        .reset_index()
    )

    basin35_pct_wide_df = (
        basin35_fu_all_df
        .pivot_table(index=["Region", "Basin_35"], columns="FU", values="Area_pct_of_Basin35", aggfunc="sum", fill_value=0)
        .reset_index()
    )

    mu48_area_wide_df = (
        mu48_fu_all_df
        .pivot_table(index=["Region", "Manag_Unit_48"], columns="FU", values="Area_ha", aggfunc="sum", fill_value=0)
        .reset_index()
    )

    mu48_pct_wide_df = (
        mu48_fu_all_df
        .pivot_table(index=["Region", "Manag_Unit_48"], columns="FU", values="Area_pct_of_MU48", aggfunc="sum", fill_value=0)
        .reset_index()
    )

    qa_summary_df = pd.DataFrame(qa_summary_rows).sort_values("Region")

    return {
        "fu_area_all": fu_area_all_df,
        "subcat_fu": subcat_fu_all_df.sort_values(["Region", "ModelElement", "FU"]),
        "basin35_fu": basin35_fu_all_df.sort_values(["Region", "Basin_35", "FU"]),
        "mu48_fu": mu48_fu_all_df.sort_values(["Region", "Manag_Unit_48", "FU"]),
        "basin35_area_wide": basin35_area_wide_df.sort_values(["Region", "Basin_35"]),
        "basin35_pct_wide": basin35_pct_wide_df.sort_values(["Region", "Basin_35"]),
        "mu48_area_wide": mu48_area_wide_df.sort_values(["Region", "Manag_Unit_48"]),
        "mu48_pct_wide": mu48_pct_wide_df.sort_values(["Region", "Manag_Unit_48"]),
        "region_fu": region_fu_all_df.sort_values(["Region", "FU"]),
        "qa_summary": qa_summary_df,
    }


# =========================================================
# Rainfall summary
# =========================================================

def prepare_region_rainfall_table(
    climate_df_raw: pd.DataFrame,
    fu_areas_df_raw: pd.DataFrame,
    reg_lut_raw: pd.DataFrame,
    region: str,
    n_years: float = 30.0,
) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], Dict[str, float]]:
    reg_lut, lut_dup_before = _normalise_lut(
        reg_lut_raw=reg_lut_raw,
        region=region,
        require_mu48=False,
    )

    climate_key_col = find_column(
        climate_df_raw,
        ["Catchment", "ModelElement", "SUBCAT", "Subcat", "Reg_SC"],
        "climate_df",
    )
    climate_fu_col = find_column(climate_df_raw, ["FU", "Functional Unit"], "climate_df")
    climate_element_col = find_column(climate_df_raw, ["Element"], "climate_df")
    climate_rain_col = find_column(
        climate_df_raw,
        ["Depth_m", "Depth (m)", "Value", "Rainfall_m"],
        "climate_df",
    )

    fuarea_key_col = find_column(
        fu_areas_df_raw,
        ["Catchment", "ModelElement", "SUBCAT", "Subcat", "Reg_SC"],
        "fuAreas_df",
    )
    fuarea_fu_col = find_column(fu_areas_df_raw, ["FU", "Functional Unit"], "fuAreas_df")
    fuarea_area_col = find_column(fu_areas_df_raw, ["Area", "Area_m2", "Area (m2)"], "fuAreas_df")

    climate_df = climate_df_raw.rename(
        columns={
            climate_key_col: "ModelElement",
            climate_fu_col: "FU",
            climate_element_col: "Element",
            climate_rain_col: "Rainfall_m_total",
        }
    ).copy()

    fu_areas_df = fu_areas_df_raw.rename(
        columns={
            fuarea_key_col: "ModelElement",
            fuarea_fu_col: "FU",
            fuarea_area_col: "Area_m2",
        }
    ).copy()

    climate_df["ModelElement"] = _normalise_id(climate_df["ModelElement"])
    climate_df["FU"] = climate_df["FU"].astype(str).str.strip()
    fu_areas_df["ModelElement"] = _normalise_id(fu_areas_df["ModelElement"])
    fu_areas_df["FU"] = fu_areas_df["FU"].astype(str).str.strip()

    climate_rain_df = climate_df.loc[
        climate_df["Element"].astype(str).str.strip().str.lower() == "rainfall",
        ["ModelElement", "FU", "Rainfall_m_total"],
    ].copy()

    climate_rain_df["Rainfall_m_total"] = pd.to_numeric(climate_rain_df["Rainfall_m_total"], errors="coerce").fillna(0.0)
    climate_rain_df["Rainfall_mm_total"] = climate_rain_df["Rainfall_m_total"] * 1000.0
    climate_rain_df["Rainfall_mm_annual"] = climate_rain_df["Rainfall_mm_total"] / n_years

    fu_areas_df = fu_areas_df[["ModelElement", "FU", "Area_m2"]].copy()
    fu_areas_df["Area_m2"] = pd.to_numeric(fu_areas_df["Area_m2"], errors="coerce").fillna(0.0)

    climate_dups = _check_duplicates(climate_rain_df, ["ModelElement", "FU"])
    fuarea_dups = _check_duplicates(fu_areas_df, ["ModelElement", "FU"])

    climate_rain_df = (
        climate_rain_df
        .groupby(["ModelElement", "FU"], as_index=False)
        .agg(
            Rainfall_m_total=("Rainfall_m_total", "max"),
            Rainfall_mm_total=("Rainfall_mm_total", "max"),
            Rainfall_mm_annual=("Rainfall_mm_annual", "max"),
        )
    )

    fu_areas_df = (
        fu_areas_df
        .groupby(["ModelElement", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )

    key_check = pd.merge(
        climate_rain_df[["ModelElement", "FU"]],
        fu_areas_df[["ModelElement", "FU"]],
        on=["ModelElement", "FU"],
        how="outer",
        indicator=True,
    )

    rain_area_df = pd.merge(climate_rain_df, fu_areas_df, on=["ModelElement", "FU"], how="inner")

    if rain_area_df.empty:
        raise ValueError(f"No rows after joining rainfall and FU area for region {region}")

    area_after_fu_merge = float(rain_area_df["Area_m2"].sum())

    rain_area_df = pd.merge(rain_area_df, reg_lut, on="ModelElement", how="left")

    area_after_lut_merge = float(rain_area_df["Area_m2"].sum())
    unmatched_lut_df = rain_area_df[rain_area_df["Basin_35"].isna()].copy()

    rain_area_df = rain_area_df[rain_area_df["Area_m2"] > 0].copy()

    inconsistent_rain_df = _check_rainfall_consistency(rain_area_df)

    rain_area_df["rain_x_area_total"] = rain_area_df["Rainfall_mm_total"] * rain_area_df["Area_m2"]
    rain_area_df["rain_x_area_annual"] = rain_area_df["Rainfall_mm_annual"] * rain_area_df["Area_m2"]

    qa_tables = {
        "lut_dup_before": lut_dup_before,
        "climate_dups": climate_dups,
        "fuarea_dups": fuarea_dups,
        "unmatched_lut": unmatched_lut_df,
        "inconsistent_rain": inconsistent_rain_df,
        "key_check": key_check,
    }

    qa_metrics = {
        "Area_after_climate_area_merge_m2": area_after_fu_merge,
        "Area_after_LUT_merge_m2": area_after_lut_merge,
        "Unmatched_LUT_rows": float(len(unmatched_lut_df)),
        "Rainfall_inconsistent_ModelElements": float(len(inconsistent_rain_df)),
    }

    return rain_area_df, qa_tables, qa_metrics


def collapse_region_rainfall_outputs(
    rain_area_df: pd.DataFrame,
) -> Dict[str, pd.DataFrame]:
    subcat_group_cols = ["ModelElement", "Basin_35", "Region"]
    if "Manag_Unit_48" in rain_area_df.columns:
        subcat_group_cols.append("Manag_Unit_48")

    subcat_df = (
        rain_area_df
        .groupby(subcat_group_cols, as_index=False)
        .agg(
            SubcatArea_m2=("Area_m2", "sum"),
            Rainfall_mm_total=("Rainfall_mm_total", "max"),
            Rainfall_mm_annual=("Rainfall_mm_annual", "max"),
        )
    )

    subcat_df["rain_x_area_total"] = subcat_df["Rainfall_mm_total"] * subcat_df["SubcatArea_m2"]
    subcat_df["rain_x_area_annual"] = subcat_df["Rainfall_mm_annual"] * subcat_df["SubcatArea_m2"]

    basin_df = (
        subcat_df
        .groupby(["Basin_35", "Region"], as_index=False)
        .agg(
            BasinArea_m2=("SubcatArea_m2", "sum"),
            BasinRainArea_total=("rain_x_area_total", "sum"),
            BasinRainArea_annual=("rain_x_area_annual", "sum"),
        )
    )
    basin_df["annual_rainfall_mm"] = _safe_divide(basin_df["BasinRainArea_annual"], basin_df["BasinArea_m2"])
    basin_df["total_rainfall_mm_30yr"] = _safe_divide(basin_df["BasinRainArea_total"], basin_df["BasinArea_m2"])
    basin_df["BasinArea_km2"] = basin_df["BasinArea_m2"] / 1e6

    if "Manag_Unit_48" in subcat_df.columns:
        mu48_df = (
            subcat_df
            .dropna(subset=["Manag_Unit_48"])
            .groupby(["Manag_Unit_48", "Region"], as_index=False)
            .agg(
                MU48Area_m2=("SubcatArea_m2", "sum"),
                MU48RainArea_total=("rain_x_area_total", "sum"),
                MU48RainArea_annual=("rain_x_area_annual", "sum"),
            )
        )
        mu48_df["annual_rainfall_mm"] = _safe_divide(mu48_df["MU48RainArea_annual"], mu48_df["MU48Area_m2"])
        mu48_df["total_rainfall_mm_30yr"] = _safe_divide(mu48_df["MU48RainArea_total"], mu48_df["MU48Area_m2"])
        mu48_df["MU48Area_km2"] = mu48_df["MU48Area_m2"] / 1e6
    else:
        mu48_df = pd.DataFrame(
            columns=[
                "Manag_Unit_48",
                "Region",
                "MU48Area_m2",
                "MU48RainArea_total",
                "MU48RainArea_annual",
                "annual_rainfall_mm",
                "total_rainfall_mm_30yr",
                "MU48Area_km2",
            ]
        )

    return {
        "rain_area": rain_area_df,
        "subcat": subcat_df,
        "basin35": basin_df,
        "mu48": mu48_df,
    }


def build_rainfall_summary_across_regions(
    climate_tables_by_region: Dict[str, pd.DataFrame],
    fu_area_tables_by_region: Dict[str, pd.DataFrame],
    reg_lut_tables_by_region: Dict[str, pd.DataFrame],
    region_order: Optional[List[str]] = None,
    n_years: float = 30.0,
) -> Dict[str, pd.DataFrame]:
    if region_order is None:
        region_order = list(climate_tables_by_region.keys())

    rainfall_by_region = {}
    subcat_by_region = {}
    basin_by_region = {}
    mu48_by_region = {}

    qa_summary_rows = []
    qa_key_check_frames = []
    qa_unmatched_frames = []
    qa_inconsistent_frames = []

    for region in region_order:
        rain_area_df, qa_tables, qa_metrics = prepare_region_rainfall_table(
            climate_df_raw=climate_tables_by_region[region],
            fu_areas_df_raw=fu_area_tables_by_region[region],
            reg_lut_raw=reg_lut_tables_by_region[region],
            region=region,
            n_years=n_years,
        )

        collapsed = collapse_region_rainfall_outputs(rain_area_df)

        rainfall_by_region[region] = collapsed["rain_area"]
        subcat_by_region[region] = collapsed["subcat"]
        basin_by_region[region] = collapsed["basin35"]
        mu48_by_region[region] = collapsed["mu48"]

        key_check = qa_tables["key_check"].copy()
        key_check.insert(0, "Region", region)
        qa_key_check_frames.append(key_check)

        unmatched = qa_tables["unmatched_lut"].copy()
        if not unmatched.empty:
            unmatched.insert(0, "Region_QA", region)
            qa_unmatched_frames.append(unmatched)

        inconsistent = qa_tables["inconsistent_rain"].copy()
        if not inconsistent.empty:
            inconsistent.insert(0, "Region_QA", region)
            qa_inconsistent_frames.append(inconsistent)

        qa_summary_rows.append({
            "Region": region,
            "LUT_dup_ModelElement_before_dedup": len(qa_tables["lut_dup_before"][["ModelElement"]].drop_duplicates()) if not qa_tables["lut_dup_before"].empty else 0,
            "Climate_dup_ModelElement_FU_keys": len(qa_tables["climate_dups"][["ModelElement", "FU"]].drop_duplicates()) if not qa_tables["climate_dups"].empty else 0,
            "FUArea_dup_ModelElement_FU_keys": len(qa_tables["fuarea_dups"][["ModelElement", "FU"]].drop_duplicates()) if not qa_tables["fuarea_dups"].empty else 0,
            "Area_after_climate_area_merge_m2": qa_metrics["Area_after_climate_area_merge_m2"],
            "Area_after_LUT_merge_m2": qa_metrics["Area_after_LUT_merge_m2"],
            "Unmatched_LUT_rows": int(qa_metrics["Unmatched_LUT_rows"]),
            "Rainfall_inconsistent_ModelElements": int(qa_metrics["Rainfall_inconsistent_ModelElements"]),
            "Subcat_count": len(collapsed["subcat"]),
            "Basin_count": len(collapsed["basin35"]),
            "MU48_count": len(collapsed["mu48"]),
        })

    rain_all_df = pd.concat([rainfall_by_region[r] for r in region_order], ignore_index=True)
    subcat_all_df = pd.concat([subcat_by_region[r] for r in region_order], ignore_index=True)
    basin35_df = pd.concat([basin_by_region[r] for r in region_order], ignore_index=True)
    mu48_df = pd.concat([mu48_by_region[r] for r in region_order], ignore_index=True)

    basin35_df = basin35_df[
        ["Region", "Basin_35", "annual_rainfall_mm", "total_rainfall_mm_30yr", "BasinArea_m2", "BasinArea_km2"]
    ].sort_values(["Region", "Basin_35"])

    region_df = (
        subcat_all_df
        .groupby("Region", as_index=False)
        .agg(
            RegionArea_m2=("SubcatArea_m2", "sum"),
            RegionRainArea_total=("rain_x_area_total", "sum"),
            RegionRainArea_annual=("rain_x_area_annual", "sum"),
        )
    )
    region_df["annual_rainfall_mm"] = _safe_divide(region_df["RegionRainArea_annual"], region_df["RegionArea_m2"])
    region_df["total_rainfall_mm_30yr"] = _safe_divide(region_df["RegionRainArea_total"], region_df["RegionArea_m2"])
    region_df["RegionArea_km2"] = region_df["RegionArea_m2"] / 1e6
    region_df = region_df[
        ["Region", "annual_rainfall_mm", "total_rainfall_mm_30yr", "RegionArea_m2", "RegionArea_km2"]
    ].sort_values("Region")

    gbr_df = (
        subcat_all_df
        .groupby(lambda _: 0)
        .agg(
            GBRArea_m2=("SubcatArea_m2", "sum"),
            GBRRainArea_total=("rain_x_area_total", "sum"),
            GBRRainArea_annual=("rain_x_area_annual", "sum"),
        )
        .reset_index(drop=True)
    )
    gbr_df["annual_rainfall_mm"] = _safe_divide(gbr_df["GBRRainArea_annual"], gbr_df["GBRArea_m2"])
    gbr_df["total_rainfall_mm_30yr"] = _safe_divide(gbr_df["GBRRainArea_total"], gbr_df["GBRArea_m2"])
    gbr_df["GBRArea_km2"] = gbr_df["GBRArea_m2"] / 1e6
    gbr_df.insert(0, "Region", "GBR")
    gbr_df = gbr_df[
        ["Region", "annual_rainfall_mm", "total_rainfall_mm_30yr", "GBRArea_m2", "GBRArea_km2"]
    ]

    if not mu48_df.empty:
        mu48_df = mu48_df[
            ["Region", "Manag_Unit_48", "annual_rainfall_mm", "total_rainfall_mm_30yr", "MU48Area_m2", "MU48Area_km2"]
        ].sort_values(["Region", "Manag_Unit_48"])

    subcat_out_cols = ["Region", "ModelElement", "Basin_35", "Rainfall_mm_annual", "Rainfall_mm_total", "SubcatArea_m2"]
    if "Manag_Unit_48" in subcat_all_df.columns:
        subcat_out_cols.insert(3, "Manag_Unit_48")

    subcat_out_df = subcat_all_df[subcat_out_cols].sort_values(["Region", "ModelElement"])
    qa_summary_df = pd.DataFrame(qa_summary_rows).sort_values("Region")

    return {
        "rain_all": rain_all_df,
        "subcat": subcat_out_df,
        "basin35": basin35_df,
        "region": region_df,
        "gbr": gbr_df,
        "mu48": mu48_df,
        "qa_summary": qa_summary_df,
        "qa_key_check": pd.concat(qa_key_check_frames, ignore_index=True) if qa_key_check_frames else pd.DataFrame(),
        "qa_unmatched_lut": pd.concat(qa_unmatched_frames, ignore_index=True) if qa_unmatched_frames else pd.DataFrame(),
        "qa_inconsistent_rain": pd.concat(qa_inconsistent_frames, ignore_index=True) if qa_inconsistent_frames else pd.DataFrame(),
    }


# =========================================================
# Combined package workflow
# =========================================================

def build_landuse_rainfall_summary(
    cfg: GBRConfig,
    regions: list[str] | None = None,
    model: str = DEFAULT_MODEL,
) -> Dict[str, pd.DataFrame]:
    selected = _selected_regions(cfg, regions)

    fu_area_tables, climate_tables, parameter_tables, reg_lut_tables = load_landuse_rainfall_inputs(
        cfg=cfg,
        regions=selected,
        model=model,
    )

    land_use_stream = build_land_use_stream_summary(
        fu_area_tables_by_region=fu_area_tables,
        parameter_tables_by_region=parameter_tables,
        region_order=selected,
    )

    landuse = build_land_use_detailed_summary_across_regions(
        fu_area_tables_by_region=fu_area_tables,
        reg_lut_tables_by_region=reg_lut_tables,
        region_order=selected,
        fus_of_interest=None,
    )

    rainfall = build_rainfall_summary_across_regions(
        climate_tables_by_region=climate_tables,
        fu_area_tables_by_region=fu_area_tables,
        reg_lut_tables_by_region=reg_lut_tables,
        region_order=selected,
        n_years=_cfg_model_years(cfg),
    )

    basin35_rainfall_landuse = pd.merge(
        rainfall["basin35"],
        landuse["basin35_area_wide"],
        on=["Region", "Basin_35"],
        how="left",
    )

    mu48_rainfall_landuse = pd.merge(
        rainfall["mu48"],
        landuse["mu48_area_wide"],
        on=["Region", "Manag_Unit_48"],
        how="left",
    )

    qa_summary = pd.merge(
        landuse["qa_summary"],
        rainfall["qa_summary"],
        on="Region",
        how="outer",
        suffixes=("_landuse", "_rainfall"),
    )

    return {
        "land_use_stream_summary": land_use_stream,
        "fu_area_all": landuse["fu_area_all"],
        "subcat_fu_area": landuse["subcat_fu"],
        "basin35_fu_area": landuse["basin35_fu"],
        "mu48_fu_area": landuse["mu48_fu"],
        "region_fu_area": landuse["region_fu"],
        "basin35_area_wide": landuse["basin35_area_wide"],
        "basin35_pct_wide": landuse["basin35_pct_wide"],
        "mu48_area_wide": landuse["mu48_area_wide"],
        "mu48_pct_wide": landuse["mu48_pct_wide"],
        "rainfall_all": rainfall["rain_all"],
        "rainfall_subcat": rainfall["subcat"],
        "rainfall_basin35": rainfall["basin35"],
        "rainfall_mu48": rainfall["mu48"],
        "rainfall_region": rainfall["region"],
        "rainfall_gbr": rainfall["gbr"],
        "landuse_rainfall_basin35": basin35_rainfall_landuse,
        "landuse_rainfall_mu48": mu48_rainfall_landuse,
        "qa_summary": qa_summary,
        "qa_key_check": rainfall["qa_key_check"],
        "qa_unmatched_lut": rainfall["qa_unmatched_lut"],
        "qa_inconsistent_rain": rainfall["qa_inconsistent_rain"],
    }


def run_landuse_rainfall_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    regions: list[str] | None = None,
    bundle_dirs: dict[str, Path] | None = None,
) -> dict[str, object]:
    """
    Bundle-compatible runner.

    Arguments constituents, value_column, units and bundle_dirs are accepted
    for wrapper compatibility.
    """
    out_dir = ensure_output_dir(output_dir)

    model = process_model or DEFAULT_MODEL

    result = build_landuse_rainfall_summary(
        cfg=cfg,
        regions=regions if regions is not None else getattr(cfg, "regions", None),
        model=model,
    )

    files: dict[str, Path] = {}

    csv_outputs = {
        "landuse_stream_summary_csv": ("land_use_stream_summary", "landuse_stream_summary.csv"),
        "landuse_fu_area_all_csv": ("fu_area_all", "landuse_fu_area_all.csv"),
        "landuse_subcat_fu_area_csv": ("subcat_fu_area", "landuse_subcat_fu_area.csv"),
        "landuse_basin35_fu_area_csv": ("basin35_fu_area", "landuse_basin35_fu_area.csv"),
        "landuse_mu48_fu_area_csv": ("mu48_fu_area", "landuse_mu48_fu_area.csv"),
        "landuse_region_fu_area_csv": ("region_fu_area", "landuse_region_fu_area.csv"),
        "landuse_basin35_area_wide_csv": ("basin35_area_wide", "landuse_basin35_area_wide.csv"),
        "landuse_basin35_pct_wide_csv": ("basin35_pct_wide", "landuse_basin35_pct_wide.csv"),
        "landuse_mu48_area_wide_csv": ("mu48_area_wide", "landuse_mu48_area_wide.csv"),
        "landuse_mu48_pct_wide_csv": ("mu48_pct_wide", "landuse_mu48_pct_wide.csv"),
        "rainfall_all_csv": ("rainfall_all", "rainfall_all.csv"),
        "rainfall_subcat_csv": ("rainfall_subcat", "rainfall_subcat.csv"),
        "rainfall_basin35_csv": ("rainfall_basin35", "rainfall_basin35.csv"),
        "rainfall_mu48_csv": ("rainfall_mu48", "rainfall_mu48.csv"),
        "rainfall_region_csv": ("rainfall_region", "rainfall_region.csv"),
        "rainfall_gbr_csv": ("rainfall_gbr", "rainfall_gbr.csv"),
        "landuse_rainfall_basin35_csv": ("landuse_rainfall_basin35", "landuse_rainfall_basin35.csv"),
        "landuse_rainfall_mu48_csv": ("landuse_rainfall_mu48", "landuse_rainfall_mu48.csv"),
        "landuse_rainfall_qa_csv": ("qa_summary", "landuse_rainfall_qa_summary.csv"),
    }

    for file_key, (table_key, filename) in csv_outputs.items():
        df = result.get(table_key, pd.DataFrame())
        path = out_dir / filename
        df.to_csv(path, index=False)
        files[file_key] = path

    optional_csv_outputs = {
        "landuse_rainfall_qa_key_check_csv": ("qa_key_check", "qa_key_check_climate_vs_fuarea.csv"),
        "landuse_rainfall_qa_unmatched_lut_csv": ("qa_unmatched_lut", "qa_unmatched_lut.csv"),
        "landuse_rainfall_qa_inconsistent_rain_csv": ("qa_inconsistent_rain", "qa_inconsistent_rain.csv"),
    }

    for file_key, (table_key, filename) in optional_csv_outputs.items():
        df = result.get(table_key, pd.DataFrame())
        if not df.empty:
            path = out_dir / filename
            df.to_csv(path, index=False)
            files[file_key] = path

    workbook_path = out_dir / "landuse_rainfall_summary.xlsx"
    export_tables_to_excel(
        tables={
            "qa_summary": result["qa_summary"],
            "landuse_stream": result["land_use_stream_summary"],
            "rainfall_region": result["rainfall_region"],
            "rainfall_gbr": result["rainfall_gbr"],
            "rainfall_basin35": result["rainfall_basin35"],
            "rainfall_mu48": result["rainfall_mu48"],
            "landuse_region_fu": result["region_fu_area"],
            "landuse_basin35_fu": result["basin35_fu_area"],
            "landuse_mu48_fu": result["mu48_fu_area"],
            "basin35_area_wide": result["basin35_area_wide"],
            "basin35_pct_wide": result["basin35_pct_wide"],
            "mu48_area_wide": result["mu48_area_wide"],
            "mu48_pct_wide": result["mu48_pct_wide"],
            "combined_basin35": result["landuse_rainfall_basin35"],
            "combined_mu48": result["landuse_rainfall_mu48"],
        },
        output_path=workbook_path,
        index=False,
    )
    files["landuse_rainfall_workbook"] = workbook_path

    result["files"] = files
    return result


def export_landuse_rainfall_summary(*args: Any, **kwargs: Any) -> dict[str, object]:
    return run_landuse_rainfall_summary(*args, **kwargs)