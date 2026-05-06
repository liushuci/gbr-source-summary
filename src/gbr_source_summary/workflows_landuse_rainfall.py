from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# =========================================================
# Defaults / constants
# =========================================================

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

KT_CONSTITUENTS = ["FS"]
# =========================================================
# Generic helpers
# =========================================================

def find_column(df: pd.DataFrame, candidates: List[str], df_name: str = "dataframe") -> str:
    for col in candidates:
        if col in df.columns:
            return col
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


def _normalise_lut(
    reg_lut_raw: pd.DataFrame,
    region: str,
    require_mu48: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Standardise LUT columns to:
    - ModelElement
    - Basin_35
    - Manag_Unit_48 (if present)
    - Region
    """
    lut_key_col = find_column(
        reg_lut_raw,
        ["ModelElement", "SUBCAT", "Subcat", "subcat"],
        "regLUT",
    )
    lut_basin35_col = find_column(
        reg_lut_raw,
        ["Basin_35", "Basin35", "Basin"],
        "regLUT",
    )

    lut_mu48_col = None
    for c in ["Manag_Unit_48", "Manag Unit 48", "Management_Unit_48"]:
        if c in reg_lut_raw.columns:
            lut_mu48_col = c
            break

    if require_mu48 and lut_mu48_col is None:
        raise KeyError(f"No Manag_Unit_48 column found in LUT for {region}")

    reg_lut = reg_lut_raw.rename(columns={
        lut_key_col: "ModelElement",
        lut_basin35_col: "Basin_35",
    }).copy()

    if lut_mu48_col is not None:
        reg_lut = reg_lut.rename(columns={lut_mu48_col: "Manag_Unit_48"})

    reg_lut["Region"] = region

    keep_cols = ["ModelElement", "Basin_35", "Region"]
    if "Manag_Unit_48" in reg_lut.columns:
        keep_cols.append("Manag_Unit_48")

    lut_dup_before = _check_duplicates(
        reg_lut[keep_cols].copy(),
        ["ModelElement"],
    )

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
    """
    Build one-region FU area summary from fuAreasTable.

    Returns
    -------
    DataFrame
        Index = FU categories
        Column = single value column named 'Area_m2'
    """
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
    _ensure_columns(parameter_table, [parameter_col, value_col], "parameter_table")

    lengths = parameter_table.loc[
        parameter_table[parameter_col].astype(str).str.strip() == target_parameter,
        [value_col]
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
        "Sugarcane": "Sugracane (ha)",
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
    """
    Prepare merged FU-area-LUT table for one region.

    Returns
    -------
    fu_area_df : DataFrame
        Positive-area merged FU table at ModelElement-FU level.
    qa_tables : dict[str, DataFrame]
    qa_metrics : dict[str, float]
    """
    reg_lut, lut_dup_before = _normalise_lut(
        reg_lut_raw=reg_lut_raw,
        region=region,
        require_mu48=True,
    )

    fuarea_key_col = find_column(
        fu_areas_df_raw,
        ["Catchment", "ModelElement", "SUBCAT", "Subcat"],
        "fuAreas_df",
    )
    fuarea_fu_col = find_column(fu_areas_df_raw, ["FU", "Functional Unit"], "fuAreas_df")
    fuarea_area_col = find_column(fu_areas_df_raw, ["Area", "Area_m2", "Area (m2)"], "fuAreas_df")

    fu_areas_df = fu_areas_df_raw.rename(columns={
        fuarea_key_col: "ModelElement",
        fuarea_fu_col: "FU",
        fuarea_area_col: "Area_m2",
    }).copy()

    fu_areas_df = fu_areas_df[["ModelElement", "FU", "Area_m2"]].copy()

    if fus_of_interest is not None:
        fu_areas_df = fu_areas_df[fu_areas_df["FU"].isin(fus_of_interest)].copy()

    fuarea_dups = _check_duplicates(fu_areas_df, ["ModelElement", "FU"])

    fu_areas_df = (
        fu_areas_df
        .groupby(["ModelElement", "FU"], as_index=False)
        .agg(Area_m2=("Area_m2", "sum"))
    )

    area_before_lut_merge = float(fu_areas_df["Area_m2"].sum())

    fu_area_df = pd.merge(
        fu_areas_df,
        reg_lut,
        on="ModelElement",
        how="left",
    )

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
    """
    Create ModelElement×FU / MU48×FU / Region×FU summaries for one region.
    """
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
    subcat_fu_df = pd.merge(
        subcat_fu_df,
        subcat_total_area,
        on=["Region", "ModelElement"],
        how="left",
    )
    subcat_fu_df["Area_pct_of_SUBCAT"] = (
        subcat_fu_df["Area_m2"] / subcat_fu_df["SubcatTotalArea_m2"] * 100.0
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
    mu48_fu_df = pd.merge(
        mu48_fu_df,
        mu48_total_area,
        on=["Region", "Manag_Unit_48"],
        how="left",
    )
    mu48_fu_df["Area_pct_of_MU48"] = (
        mu48_fu_df["Area_m2"] / mu48_fu_df["MU48TotalArea_m2"] * 100.0
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
    region_fu_df = pd.merge(
        region_fu_df,
        region_total_area,
        on="Region",
        how="left",
    )
    region_fu_df["Area_pct_of_Region"] = (
        region_fu_df["Area_m2"] / region_fu_df["RegionTotalArea_m2"] * 100.0
    )

    return {
        "fu_area": fu_area_df,
        "subcat_fu": subcat_fu_df,
        "mu48_fu": mu48_fu_df,
        "region_fu": region_fu_df,
    }


def _build_single_constituent_fu_summary(
    region_values_by_region: Dict[str, pd.Series | dict | pd.DataFrame],
    region_order: List[str],
    region_name_map: Optional[Dict[str, str]] = None,
    fu_order: Optional[List[str]] = None,
    fill_value: float = 0.0,
) -> pd.DataFrame:
    if region_name_map is None:
        region_name_map = REGION_NAME_MAP
    if fu_order is None:
        fu_order = FU_LOAD_ORDER

    rows = []

    for region in region_order:
        obj = region_values_by_region[region]

        if isinstance(obj, pd.Series):
            s = obj.copy()
        elif isinstance(obj, dict):
            s = pd.Series(obj, dtype=float)
        elif isinstance(obj, pd.DataFrame):
            if obj.shape[0] == 1:
                s = obj.iloc[0].copy()
            elif obj.shape[1] == 1:
                s = obj.iloc[:, 0].copy()
            else:
                raise ValueError(
                    f"Region {region} DataFrame must be single-row or single-column. Got shape={obj.shape}"
                )
        else:
            raise TypeError(f"Unsupported regional object type for {region}: {type(obj)}")

        s.index = s.index.astype(str)

        if "Dryland Cropping" in s.index or "Irrigated Cropping" in s.index:
            s["Cropping"] = s.get("Dryland Cropping", 0) + s.get("Irrigated Cropping", 0)

        if "Urban + Other" not in s.index:
            s["Urban + Other"] = s.get("Urban", 0) + s.get("Other", 0)

        for fu in fu_order:
            if fu not in s.index:
                s[fu] = fill_value

        s = s[fu_order]
        s.name = region
        rows.append(s)

    out = pd.DataFrame(rows)
    out.loc["GBR"] = out.fillna(fill_value).sum(axis=0)

    pretty_index = [region_name_map.get(r, r) for r in region_order] + ["GBR"]
    out.index = pretty_index

    return out.fillna(fill_value)


def build_fu_load_summary_tables(
    region_load_to_regexport_fu: Dict[str, Dict[str, Dict[str, pd.Series | dict | pd.DataFrame]]],
    constituents: List[str],
    region_order: List[str],
    scenario: str = "BASE",
    fu_order: Optional[List[str]] = None,
    kg_to_kt: float = 1e-6,
    kg_to_t: float = 1e-3,
    per_year: float = 1.0,
    kt_constituents: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    if fu_order is None:
        fu_order = FU_LOAD_ORDER
    if kt_constituents is None:
        kt_constituents = KT_CONSTITUENTS

    results: Dict[str, pd.DataFrame] = {}

    for con in constituents:
        region_values = {}

        for region in region_order:
            raw = region_load_to_regexport_fu[region][scenario][con]

            if isinstance(raw, pd.DataFrame):
                if raw.shape[0] == 1:
                    s = raw.iloc[0].copy()
                elif raw.shape[1] == 1:
                    s = raw.iloc[:, 0].copy()
                else:
                    s = raw.squeeze()
            elif isinstance(raw, pd.Series):
                s = raw.copy()
            elif isinstance(raw, dict):
                s = pd.Series(raw, dtype=float)
            else:
                raise TypeError(
                    f"Unsupported load object type for region={region}, constituent={con}: {type(raw)}"
                )

            factor = kg_to_kt * per_year if con in kt_constituents else kg_to_t * per_year
            s = pd.to_numeric(s, errors="coerce") * factor
            region_values[region] = s

        df = _build_single_constituent_fu_summary(
            region_values_by_region=region_values,
            region_order=region_order,
            fu_order=fu_order,
            fill_value=0.0,
        )

        if con in kt_constituents:
            df.columns = [
                "Banana (kt/year)",
                "Conservation (kt/year)",
                "Cropping (kt/year)",
                "Dairy (kt/year)",
                "Forestry (kt/year)",
                "Grazing (kt/year)",
                "Horticulture (kt/year)",
                "Stream (kt/year)",
                "Sugracane (kt/year)",
                "Urban + Other (kt/year)",
            ]
        else:
            df.columns = [
                "Banana (t/year)",
                "Conservation (t/year)",
                "Cropping (t/year)",
                "Dairy (t/year)",
                "Forestry (t/year)",
                "Grazing (t/year)",
                "Horticulture (t/year)",
                "Stream (t/year)",
                "Sugracane (t/year)",
                "Urban + Other (t/year)",
            ]

        results[con] = df.fillna(0).round(2)

    return results


def build_fu_areal_load_summary_tables(
    fu_load_summary_tables: Dict[str, pd.DataFrame],
    fu_area_summary: pd.DataFrame,
    constituents: List[str],
    t_to_kg: float = 1000.0,
    kt_to_t: float = 1000.0,
    kt_constituents: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    if kt_constituents is None:
        kt_constituents = KT_CONSTITUENTS

    results: Dict[str, pd.DataFrame] = {}

    area_values = fu_area_summary.values.astype(float)

    for con in constituents:
        load_df = fu_load_summary_tables[con].copy()
        load_values = load_df.values.astype(float)

        with np.errstate(divide="ignore", invalid="ignore"):
            if con in kt_constituents:
                areal_values = (load_values * kt_to_t) / area_values
            else:
                areal_values = (load_values * t_to_kg) / area_values

        areal_values = np.where(np.isfinite(areal_values), areal_values, 0.0)

        out = pd.DataFrame(
            areal_values,
            index=load_df.index,
            columns=load_df.columns,
        ).round(3)

        if con in kt_constituents:
            out.columns = [
                "Banana (t/ha/year)",
                "Conservation (t/ha/year)",
                "Cropping (t/ha/year)",
                "Dairy (t/ha/year)",
                "Forestry (t/ha/year)",
                "Grazing (t/ha/year)",
                "Horticulture (t/ha/year)",
                "Stream (t/km/year)",
                "Sugracane (t/ha/year)",
                "Urban + Other (t/ha/year)",
            ]
        else:
            out.columns = [
                "Banana (kg/ha/year)",
                "Conservation (kg/ha/year)",
                "Cropping (kg/ha/year)",
                "Dairy (kg/ha/year)",
                "Forestry (kg/ha/year)",
                "Grazing (kg/ha/year)",
                "Horticulture (kg/ha/year)",
                "Stream (kg/km/year)",
                "Sugracane (kg/ha/year)",
                "Urban + Other (kg/ha/year)",
            ]

        results[con] = out.fillna(0)

    return results

def build_land_use_detailed_summary_across_regions(
    fu_area_tables_by_region: Dict[str, pd.DataFrame],
    reg_lut_tables_by_region: Dict[str, pd.DataFrame],
    region_order: Optional[List[str]] = None,
    fus_of_interest: Optional[List[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Full detailed land-use workflow across all 6 regions.

    Returns
    -------
    dict[str, DataFrame]
        Keys:
        - fu_area_all
        - subcat_fu
        - mu48_fu
        - mu48_area_wide
        - mu48_pct_wide
        - region_fu
        - qa_summary
    """
    if region_order is None:
        region_order = list(fu_area_tables_by_region.keys())

    fuarea_by_region = {}
    subcat_fu_by_region = {}
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
            "MU48FU_rows": len(collapsed["mu48_fu"]),
            "RegionFU_rows": len(collapsed["region_fu"]),
        })

    fu_area_all_df = pd.concat([fuarea_by_region[r] for r in region_order], ignore_index=True)
    subcat_fu_all_df = pd.concat([subcat_fu_by_region[r] for r in region_order], ignore_index=True)
    mu48_fu_all_df = pd.concat([mu48_fu_by_region[r] for r in region_order], ignore_index=True)
    region_fu_all_df = pd.concat([region_fu_by_region[r] for r in region_order], ignore_index=True)

    mu48_area_wide_df = (
        mu48_fu_all_df
        .pivot_table(
            index=["Region", "Manag_Unit_48"],
            columns="FU",
            values="Area_ha",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )

    mu48_pct_wide_df = (
        mu48_fu_all_df
        .pivot_table(
            index=["Region", "Manag_Unit_48"],
            columns="FU",
            values="Area_pct_of_MU48",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )

    mu48_total_area_df = (
        mu48_fu_all_df[["Region", "Manag_Unit_48", "MU48TotalArea_m2"]]
        .drop_duplicates()
        .copy()
    )
    mu48_total_area_df["MU48TotalArea_ha"] = mu48_total_area_df["MU48TotalArea_m2"] / 1e4
    mu48_total_area_df["MU48TotalArea_km2"] = mu48_total_area_df["MU48TotalArea_m2"] / 1e6

    mu48_area_wide_df = pd.merge(
        mu48_total_area_df[["Region", "Manag_Unit_48", "MU48TotalArea_ha", "MU48TotalArea_km2"]],
        mu48_area_wide_df,
        on=["Region", "Manag_Unit_48"],
        how="left",
    )

    mu48_pct_wide_df = pd.merge(
        mu48_total_area_df[["Region", "Manag_Unit_48"]],
        mu48_pct_wide_df,
        on=["Region", "Manag_Unit_48"],
        how="left",
    )

    qa_summary_df = pd.DataFrame(qa_summary_rows).sort_values("Region")

    return {
        "fu_area_all": fu_area_all_df,
        "subcat_fu": subcat_fu_all_df.sort_values(["Region", "ModelElement", "FU"]),
        "mu48_fu": mu48_fu_all_df.sort_values(["Region", "Manag_Unit_48", "FU"]),
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
        ["Catchment", "ModelElement", "SUBCAT", "Subcat"],
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
        ["Catchment", "ModelElement", "SUBCAT", "Subcat"],
        "fuAreas_df",
    )
    fuarea_fu_col = find_column(fu_areas_df_raw, ["FU", "Functional Unit"], "fuAreas_df")
    fuarea_area_col = find_column(fu_areas_df_raw, ["Area", "Area_m2", "Area (m2)"], "fuAreas_df")

    climate_df = climate_df_raw.rename(columns={
        climate_key_col: "ModelElement",
        climate_fu_col: "FU",
        climate_element_col: "Element",
        climate_rain_col: "Rainfall_m_total",
    }).copy()

    fu_areas_df = fu_areas_df_raw.rename(columns={
        fuarea_key_col: "ModelElement",
        fuarea_fu_col: "FU",
        fuarea_area_col: "Area_m2",
    }).copy()

    climate_rain_df = climate_df.loc[
        climate_df["Element"] == "Rainfall",
        ["ModelElement", "FU", "Rainfall_m_total"]
    ].copy()

    climate_rain_df["Rainfall_mm_total"] = climate_rain_df["Rainfall_m_total"] * 1000.0
    climate_rain_df["Rainfall_mm_annual"] = climate_rain_df["Rainfall_mm_total"] / n_years

    fu_areas_df = fu_areas_df[["ModelElement", "FU", "Area_m2"]].copy()

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

    rain_area_df = pd.merge(
        climate_rain_df,
        fu_areas_df,
        on=["ModelElement", "FU"],
        how="inner",
    )

    if rain_area_df.empty:
        raise ValueError(f"No rows after joining rainfall and FU area for region {region}")

    area_after_fu_merge = float(rain_area_df["Area_m2"].sum())

    rain_area_df = pd.merge(
        rain_area_df,
        reg_lut,
        on="ModelElement",
        how="left",
    )

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
    basin_df["annual_rainfall_mm"] = basin_df["BasinRainArea_annual"] / basin_df["BasinArea_m2"]
    basin_df["total_rainfall_mm_30yr"] = basin_df["BasinRainArea_total"] / basin_df["BasinArea_m2"]
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
        mu48_df["annual_rainfall_mm"] = mu48_df["MU48RainArea_annual"] / mu48_df["MU48Area_m2"]
        mu48_df["total_rainfall_mm_30yr"] = mu48_df["MU48RainArea_total"] / mu48_df["MU48Area_m2"]
        mu48_df["MU48Area_km2"] = mu48_df["MU48Area_m2"] / 1e6
    else:
        mu48_df = pd.DataFrame(columns=[
            "Manag_Unit_48", "Region", "MU48Area_m2", "MU48RainArea_total",
            "MU48RainArea_annual", "annual_rainfall_mm",
            "total_rainfall_mm_30yr", "MU48Area_km2"
        ])

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
    region_df["annual_rainfall_mm"] = region_df["RegionRainArea_annual"] / region_df["RegionArea_m2"]
    region_df["total_rainfall_mm_30yr"] = region_df["RegionRainArea_total"] / region_df["RegionArea_m2"]
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
    gbr_df["annual_rainfall_mm"] = gbr_df["GBRRainArea_annual"] / gbr_df["GBRArea_m2"]
    gbr_df["total_rainfall_mm_30yr"] = gbr_df["GBRRainArea_total"] / gbr_df["GBRArea_m2"]
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
    }