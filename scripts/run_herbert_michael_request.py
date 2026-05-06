from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd


# =============================================================================
# Helpers
# =============================================================================

def pick_first_existing(columns: Iterable[str], candidates: list[str], label: str) -> str:
    cols_lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    raise KeyError(f"Could not find {label}. Tried: {candidates}")


def normalise_fu_name(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    mapping = {
        "Sugar Cane": "Sugarcane",
        "Sugar cane": "Sugarcane",
        "Sugarcane": "Sugarcane",
    }
    return s.replace(mapping)


def normalise_constituent_name(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    mapping = {
        "DIN": "DIN",
        "Dissolved Inorganic Nitrogen": "DIN",
        "Particulate N": "PN",
        "PN": "PN",
        "Particulate Phosphorus": "PP",
        "PP": "PP",
        "Dissolved Inorganic Phosphorus": "DIP",
        "Filterable Reactive Phosphorus": "DIP",
        "DIP": "DIP",
        "Fine Sediment": "FS",
        "Sediment - Fine": "FS",
        "FS": "FS",
    }
    return s.replace(mapping)


def normalise_budget_name(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    mapping = {
        "Hillslope": "Hillslope surface soil",
        "Hillslope surface soil": "Hillslope surface soil",
        "Gully": "Gully",
        "Streambank": "Streambank",
    }
    return s.replace(mapping)


def sum_metric(
    df: pd.DataFrame,
    group_cols: list[str],
    value_col: str,
    constituent_col: str,
    constituents: list[str],
    fu_col: str | None = None,
    fu_values: list[str] | None = None,
    budget_col: str | None = None,
    budget_values: list[str] | None = None,
) -> pd.DataFrame:
    out = df.copy()

    out = out[out[constituent_col].isin(constituents)]

    if fu_col is not None and fu_values is not None:
        out = out[out[fu_col].isin(fu_values)]

    if budget_col is not None and budget_values is not None:
        out = out[out[budget_col].isin(budget_values)]

    out = (
        out.groupby(group_cols, dropna=False)[value_col]
        .sum()
        .reset_index()
    )
    return out


# =============================================================================
# Request definitions
# =============================================================================

REQUEST_SPECS = [
    {
        "metric": "Sugar DIN (Kg/Yr)",
        "metric_code": "SugDIN_kgy",
        "fu": ["Sugarcane"],
        "constituents": ["DIN"],
        "unit": "kg/yr",
    },
    {
        "metric": "Sugar DIN (Kg/Ha/Yr)",
        "metric_code": "SugDIN_hay",
        "fu": ["Sugarcane"],
        "constituents": ["DIN"],
        "unit": "kg/ha/yr",
    },
    {
        "metric": "All Uses DIN (Kg/Yr)",
        "metric_code": "AllDIN_kgy",
        "fu": None,
        "constituents": ["DIN"],
        "unit": "kg/yr",
    },
    {
        "metric": "All Uses DIN (Kg/Ha/Yr)",
        "metric_code": "AllDIN_hay",
        "fu": None,
        "constituents": ["DIN"],
        "unit": "kg/ha/yr",
    },
    {
        "metric": "PN (Kg/Yr)",
        "metric_code": "PN_kgy",
        "fu": None,
        "constituents": ["PN"],
        "unit": "kg/yr",
    },
    {
        "metric": "PN (Kg/Ha/Yr)",
        "metric_code": "PN_hay",
        "fu": None,
        "constituents": ["PN"],
        "unit": "kg/ha/yr",
    },
    {
        "metric": "Sugar Phos (Kg/Yr)",
        "metric_code": "SugP_kgy",
        "fu": ["Sugarcane"],
        "constituents": ["DIP", "PP"],
        "unit": "kg/yr",
    },
    {
        "metric": "Sugar Phos (Kg/Ha/Yr)",
        "metric_code": "SugP_hay",
        "fu": ["Sugarcane"],
        "constituents": ["DIP", "PP"],
        "unit": "kg/ha/yr",
    },
    {
        "metric": "All Phos (Kg/Yr)",
        "metric_code": "AllP_kgy",
        "fu": None,
        "constituents": ["DIP", "PP"],
        "unit": "kg/yr",
    },
    {
        "metric": "All Phos (Kg/Ha/Yr)",
        "metric_code": "AllP_hay",
        "fu": None,
        "constituents": ["DIP", "PP"],
        "unit": "kg/ha/yr",
    },
    {
        "metric": "FS (T/Yr)",
        "metric_code": "FS_tyr",
        "fu": None,
        "constituents": ["FS"],
        "unit": "t/yr",
    },
    {
        "metric": "FS (T/Ha/Yr)",
        "metric_code": "FS_thay",
        "fu": None,
        "constituents": ["FS"],
        "unit": "t/ha/yr",
    },
]

PROCESS_SPECS = [
    {
        "metric": "Streambank (T/Yr)",
        "metric_code": "SB_tyr",
        "budget_elements": ["Streambank"],
        "constituents": ["FS"],
        "unit": "t/yr",
    },
    {
        "metric": "Streambank (T/Ha/Yr)",
        "metric_code": "SB_thay",
        "budget_elements": ["Streambank"],
        "constituents": ["FS"],
        "unit": "t/ha/yr",
    },
    {
        "metric": "Hillslope (T/Yr)",
        "metric_code": "HS_tyr",
        "budget_elements": ["Hillslope surface soil"],
        "constituents": ["FS"],
        "unit": "t/yr",
    },
    {
        "metric": "Hillslope (T/Ha/Yr)",
        "metric_code": "HS_thay",
        "budget_elements": ["Hillslope surface soil"],
        "constituents": ["FS"],
        "unit": "t/ha/yr",
    },
    {
        "metric": "Gully (T/Yr)",
        "metric_code": "GU_tyr",
        "budget_elements": ["Gully"],
        "constituents": ["FS"],
        "unit": "t/yr",
    },
    {
        "metric": "Gully (T/Ha/Yr)",
        "metric_code": "GU_thay",
        "budget_elements": ["Gully"],
        "constituents": ["FS"],
        "unit": "t/ha/yr",
    },
]


# =============================================================================
# Builders
# =============================================================================

def build_fu_request_table(
    fu_df: pd.DataFrame,
    repreg_col: str,
    area_ha_col: str,
    fu_col: str,
    constituent_col: str,
    value_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    long_tables = []

    for spec in REQUEST_SPECS:
        tmp = sum_metric(
            df=fu_df,
            group_cols=[repreg_col, area_ha_col],
            value_col=value_col,
            constituent_col=constituent_col,
            constituents=spec["constituents"],
            fu_col=fu_col,
            fu_values=spec["fu"],
        )

        if spec["unit"] == "kg/yr":
            tmp["Value"] = tmp[value_col]
        elif spec["unit"] == "kg/ha/yr":
            tmp["Value"] = tmp[value_col] / tmp[area_ha_col]
        elif spec["unit"] == "t/yr":
            tmp["Value"] = tmp[value_col] / 1000.0
        elif spec["unit"] == "t/ha/yr":
            tmp["Value"] = (tmp[value_col] / 1000.0) / tmp[area_ha_col]
        else:
            raise ValueError(f"Unexpected unit: {spec['unit']}")

        tmp = tmp[[repreg_col, "Value"]].copy()
        tmp["Metric"] = spec["metric"]
        tmp["MetricCode"] = spec["metric_code"]
        tmp["Unit"] = spec["unit"]
        long_tables.append(tmp)

    long_df = pd.concat(long_tables, ignore_index=True)

    wide_df = (
        long_df.pivot_table(
            index=repreg_col,
            columns="MetricCode",
            values="Value",
            aggfunc="first",
        )
        .reset_index()
    )
    wide_df.columns.name = None

    return long_df, wide_df


def build_process_request_table(
    proc_df: pd.DataFrame,
    repreg_col: str,
    area_ha_col: str,
    budget_col: str,
    constituent_col: str,
    value_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    long_tables = []

    for spec in PROCESS_SPECS:
        tmp = sum_metric(
            df=proc_df,
            group_cols=[repreg_col, area_ha_col],
            value_col=value_col,
            constituent_col=constituent_col,
            constituents=spec["constituents"],
            budget_col=budget_col,
            budget_values=spec["budget_elements"],
        )

        if spec["unit"] == "t/yr":
            tmp["Value"] = tmp[value_col] / 1000.0
        elif spec["unit"] == "t/ha/yr":
            tmp["Value"] = (tmp[value_col] / 1000.0) / tmp[area_ha_col]
        else:
            raise ValueError(f"Unexpected unit: {spec['unit']}")

        tmp = tmp[[repreg_col, "Value"]].copy()
        tmp["Metric"] = spec["metric"]
        tmp["MetricCode"] = spec["metric_code"]
        tmp["Unit"] = spec["unit"]
        long_tables.append(tmp)

    long_df = pd.concat(long_tables, ignore_index=True)

    wide_df = (
        long_df.pivot_table(
            index=repreg_col,
            columns="MetricCode",
            values="Value",
            aggfunc="first",
        )
        .reset_index()
    )
    wide_df.columns.name = None

    return long_df, wide_df


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build reporting-region request outputs (CSV + shapefile) from current GBR package summaries."
    )

    parser.add_argument(
        "--fu-summary-csv",
        required=True,
        help="Path to subcatchment-level FU summary CSV exported from current package.",
    )
    parser.add_argument(
        "--process-summary-csv",
        required=True,
        help="Path to subcatchment-level source/process summary CSV exported from current package.",
    )
    parser.add_argument(
        "--subcat-region-lut",
        required=True,
        help="Path to subcatchment-to-reporting-region lookup CSV.",
    )
    parser.add_argument(
        "--reporting-region-shp",
        required=True,
        help="Path to reporting-region shapefile.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory.",
    )
    parser.add_argument(
        "--target-reporting-region",
        default="Herbert",
        help="Reporting region name to export. Default: Herbert",
    )
    parser.add_argument(
        "--value-column",
        default="LoadToRegExport (kg)",
        help="Value column in the input summary CSVs. Default: LoadToRegExport (kg)",
    )

    args = parser.parse_args()

    fu_summary_csv = Path(args.fu_summary_csv)
    process_summary_csv = Path(args.process_summary_csv)
    subcat_region_lut = Path(args.subcat_region_lut)
    reporting_region_shp = Path(args.reporting_region_shp)
    output_dir = Path(args.output_dir)
    target_reporting_region = args.target_reporting_region
    default_value_column = args.value_column

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Reading inputs...")
    fu_df = pd.read_csv(fu_summary_csv)
    proc_df = pd.read_csv(process_summary_csv)
    lut_df = pd.read_csv(subcat_region_lut)
    rep_gdf = gpd.read_file(reporting_region_shp)

    # -------------------------------------------------------------------------
    # Candidate columns
    # -------------------------------------------------------------------------
    SUBCAT_COL_CANDIDATES = [
        "ModelElement",
        "Subcatchment",
        "SubCatchment",
        "Catchment",
        "SUBCAT",
        "Subcat",
        "SC",
        "Catchmt",
    ]

    REPORTING_REGION_COL_CANDIDATES = [
        "ReportingRegion",
        "SummaryRegion",
        "RepReg",
        "Basin",
        "Region",
        "MANAG_UNIT",
        "Manag_Unit_48",
    ]

    FU_COL_CANDIDATES = [
        "FU",
        "FunctionalUnit",
        "LandUse",
        "cgu",
        "CGU",
    ]

    CONSTITUENT_COL_CANDIDATES = [
        "Constituent",
        "con",
    ]

    BUDGET_ELEMENT_COL_CANDIDATES = [
        "BudgetElement",
        "Process",
        "Source",
    ]

    AREA_HA_COL_CANDIDATES = [
        "Area_ha",
        "AREA_HA",
        "AreaHa",
        "area_ha",
    ]

    # -------------------------------------------------------------------------
    # Resolve columns
    # -------------------------------------------------------------------------
    fu_subcat_col = pick_first_existing(fu_df.columns, SUBCAT_COL_CANDIDATES, "FU subcatchment column")
    proc_subcat_col = pick_first_existing(proc_df.columns, SUBCAT_COL_CANDIDATES, "process subcatchment column")
    lut_subcat_col = pick_first_existing(lut_df.columns, SUBCAT_COL_CANDIDATES, "LUT subcatchment column")

    lut_repreg_col = pick_first_existing(lut_df.columns, REPORTING_REGION_COL_CANDIDATES, "LUT reporting region column")
    shp_repreg_col = pick_first_existing(rep_gdf.columns, REPORTING_REGION_COL_CANDIDATES, "shapefile reporting region column")

    fu_fu_col = pick_first_existing(fu_df.columns, FU_COL_CANDIDATES, "FU column")
    fu_const_col = pick_first_existing(fu_df.columns, CONSTITUENT_COL_CANDIDATES, "FU constituent column")

    proc_budget_col = pick_first_existing(proc_df.columns, BUDGET_ELEMENT_COL_CANDIDATES, "process budget element column")
    proc_const_col = pick_first_existing(proc_df.columns, CONSTITUENT_COL_CANDIDATES, "process constituent column")

    if default_value_column in fu_df.columns:
        fu_value_col = default_value_column
    else:
        fu_value_col = pick_first_existing(
            fu_df.columns,
            ["LoadToRegExport (kg)", "LoadToRegExport_kg", "Value"],
            "FU value column",
        )

    if default_value_column in proc_df.columns:
        proc_value_col = default_value_column
    else:
        proc_value_col = pick_first_existing(
            proc_df.columns,
            ["LoadToRegExport (kg)", "LoadToRegExport_kg", "Value"],
            "process value column",
        )

    # -------------------------------------------------------------------------
    # Normalise values
    # -------------------------------------------------------------------------
    fu_df[fu_fu_col] = normalise_fu_name(fu_df[fu_fu_col])
    fu_df[fu_const_col] = normalise_constituent_name(fu_df[fu_const_col])

    proc_df[proc_budget_col] = normalise_budget_name(proc_df[proc_budget_col])
    proc_df[proc_const_col] = normalise_constituent_name(proc_df[proc_const_col])

    fu_df[fu_subcat_col] = fu_df[fu_subcat_col].astype(str).str.strip()
    proc_df[proc_subcat_col] = proc_df[proc_subcat_col].astype(str).str.strip()
    lut_df[lut_subcat_col] = lut_df[lut_subcat_col].astype(str).str.strip()

    lut_df[lut_repreg_col] = lut_df[lut_repreg_col].astype(str).str.strip()
    rep_gdf[shp_repreg_col] = rep_gdf[shp_repreg_col].astype(str).str.strip()

    # -------------------------------------------------------------------------
    # Attach reporting region to summary tables
    # -------------------------------------------------------------------------
    print("Joining subcatchment -> reporting region LUT...")
    lut_use = lut_df[[lut_subcat_col, lut_repreg_col]].drop_duplicates()

    fu_df = fu_df.merge(
        lut_use,
        left_on=fu_subcat_col,
        right_on=lut_subcat_col,
        how="left",
    )
    proc_df = proc_df.merge(
        lut_use,
        left_on=proc_subcat_col,
        right_on=lut_subcat_col,
        how="left",
    )

    fu_df = fu_df.rename(columns={lut_repreg_col: "ReportingRegion"})
    proc_df = proc_df.rename(columns={lut_repreg_col: "ReportingRegion"})
    rep_gdf = rep_gdf.rename(columns={shp_repreg_col: "ReportingRegion"})

    if "ReportingRegion" not in fu_df.columns or fu_df["ReportingRegion"].isna().all():
        raise ValueError("Could not attach ReportingRegion to FU summary.")
    if "ReportingRegion" not in proc_df.columns or proc_df["ReportingRegion"].isna().all():
        raise ValueError("Could not attach ReportingRegion to process summary.")

    # -------------------------------------------------------------------------
    # Aggregate total area by reporting region from LUT if available,
    # otherwise from FU summary if already present
    # -------------------------------------------------------------------------
    area_col = None
    for cand in AREA_HA_COL_CANDIDATES:
        if cand in fu_df.columns:
            area_col = cand
            break

    if area_col is None:
        for cand in AREA_HA_COL_CANDIDATES:
            if cand in lut_df.columns:
                area_col = cand
                break

    if area_col is None:
        raise KeyError(
            "Could not find an area column in FU summary or LUT. "
            "Need one of: Area_ha, AREA_HA, AreaHa, area_ha"
        )

    if area_col in lut_df.columns:
        area_by_repreg = (
            lut_df[[lut_subcat_col, lut_repreg_col, area_col]]
            .drop_duplicates(subset=[lut_subcat_col])
            .groupby(lut_repreg_col, dropna=False)[area_col]
            .sum()
            .reset_index()
            .rename(columns={lut_repreg_col: "ReportingRegion", area_col: "Area_ha"})
        )
    else:
        area_by_repreg = (
            fu_df[[fu_subcat_col, "ReportingRegion", area_col]]
            .drop_duplicates(subset=[fu_subcat_col])
            .groupby("ReportingRegion", dropna=False)[area_col]
            .sum()
            .reset_index()
            .rename(columns={area_col: "Area_ha"})
        )

    # -------------------------------------------------------------------------
    # Filter target reporting region
    # -------------------------------------------------------------------------
    print(f"Filtering to reporting region: {target_reporting_region}")
    fu_df = fu_df[fu_df["ReportingRegion"] == target_reporting_region].copy()
    proc_df = proc_df[proc_df["ReportingRegion"] == target_reporting_region].copy()
    area_by_repreg = area_by_repreg[area_by_repreg["ReportingRegion"] == target_reporting_region].copy()
    rep_gdf = rep_gdf[rep_gdf["ReportingRegion"] == target_reporting_region].copy()

    if fu_df.empty:
        raise ValueError(f"No FU rows found for reporting region '{target_reporting_region}'")
    if proc_df.empty:
        raise ValueError(f"No process rows found for reporting region '{target_reporting_region}'")
    if area_by_repreg.empty:
        raise ValueError(f"No area rows found for reporting region '{target_reporting_region}'")
    if rep_gdf.empty:
        raise ValueError(f"No shapefile features found for reporting region '{target_reporting_region}'")

    # -------------------------------------------------------------------------
    # Attach area to working tables
    # -------------------------------------------------------------------------
    fu_df = fu_df.merge(area_by_repreg, on="ReportingRegion", how="left")
    proc_df = proc_df.merge(area_by_repreg, on="ReportingRegion", how="left")

    if fu_df["Area_ha"].isna().any():
        raise ValueError("Missing Area_ha after join for FU table.")
    if proc_df["Area_ha"].isna().any():
        raise ValueError("Missing Area_ha after join for process table.")

    # -------------------------------------------------------------------------
    # Build outputs
    # -------------------------------------------------------------------------
    print("Building FU request outputs...")
    fu_long, fu_wide = build_fu_request_table(
        fu_df=fu_df,
        repreg_col="ReportingRegion",
        area_ha_col="Area_ha",
        fu_col=fu_fu_col,
        constituent_col=fu_const_col,
        value_col=fu_value_col,
    )

    print("Building process request outputs...")
    proc_long, proc_wide = build_process_request_table(
        proc_df=proc_df,
        repreg_col="ReportingRegion",
        area_ha_col="Area_ha",
        budget_col=proc_budget_col,
        constituent_col=proc_const_col,
        value_col=proc_value_col,
    )

    # -------------------------------------------------------------------------
    # Join to reporting-region shapefile
    # -------------------------------------------------------------------------
    print("Joining outputs to reporting-region shapefile...")
    fu_shp = rep_gdf.merge(fu_wide, on="ReportingRegion", how="left")
    proc_shp = rep_gdf.merge(proc_wide, on="ReportingRegion", how="left")

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------
    base_name = target_reporting_region.replace(" ", "_")

    print("Writing CSV outputs...")
    fu_long.to_csv(output_dir / f"{base_name}_FU_request_long.csv", index=False)
    fu_wide.to_csv(output_dir / f"{base_name}_FU_request_wide.csv", index=False)

    proc_long.to_csv(output_dir / f"{base_name}_process_request_long.csv", index=False)
    proc_wide.to_csv(output_dir / f"{base_name}_process_request_wide.csv", index=False)

    # optional supporting tables
    area_by_repreg.to_csv(output_dir / f"{base_name}_area_by_reporting_region.csv", index=False)

    print("Writing shapefile outputs...")
    fu_shp.to_file(output_dir / f"{base_name}_FU_request.shp")
    proc_shp.to_file(output_dir / f"{base_name}_process_request.shp")

    print("\nDone.")
    print(f"Output folder: {output_dir}")


if __name__ == "__main__":
    main()