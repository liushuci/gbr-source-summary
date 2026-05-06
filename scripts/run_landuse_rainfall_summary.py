"""
Run land use (FU area + stream length) and rainfall summary
for GBR RC13 workflow.

Outputs:
- Land use + stream summary (regional + GBR)
- Detailed land use summaries:
    - ModelElement x FU
    - MU48 x FU (long)
    - MU48 wide area table
    - MU48 wide percent table
    - Region x FU
    - QA summary
- Rainfall summaries:
    - Subcatchment / ModelElement
    - Basin35
    - MU48
    - Region (6 NRM)
    - GBR
    - QA summary
"""

from pathlib import Path
import pandas as pd

from gbr_source_summary.workflows_landuse_rainfall import (
    build_land_use_stream_summary,
    build_land_use_detailed_summary_across_regions,
    build_rainfall_summary_across_regions,
)

# =========================================================
# CONFIG
# =========================================================

RC = "Gold_93_23"
N_YEARS = 30.0

REGIONS = ["CY", "WT", "BU", "MW", "FI", "BM"]

MAIN_PATH = Path(r"F:\RC13_RC2023_24_Gold")
MODEL_PREFIX = MAIN_PATH / "Gold_ResultsSets_PointOfTruth"
REGION_DEF_PATH = MAIN_PATH / "Regions"
OUTPUT_PATH = MAIN_PATH / "report_card_summary" / "landuse_rainfall"

OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

# keep FU exactly as in Source/OpenWater
# set to None to keep all FUs
FUS_OF_INTEREST = None


# =========================================================
# HELPERS
# =========================================================

def get_reg_link_path(region: str) -> Path:
    return REGION_DEF_PATH / f"{region}_Reg_cat_node_link.csv"


def load_csv_with_fallback(path: Path, **kwargs) -> pd.DataFrame:
    """
    Read csv with normal parser first, then fallback to python engine.
    """
    try:
        return pd.read_csv(path, **kwargs)
    except Exception:
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.setdefault("engine", "python")
        fallback_kwargs.setdefault("on_bad_lines", "skip")
        return pd.read_csv(path, **fallback_kwargs)


# =========================================================
# LOADERS
# =========================================================

def load_fu_area_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for region in REGIONS:
        path = MODEL_PREFIX / region / "Model_Outputs" / f"BASE_{RC}" / "fuAreasTable.csv"
        tables[region] = load_csv_with_fallback(path)
        print(f"[{region}] fuAreas loaded: {tables[region].shape}")
    return tables


def load_parameter_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for region in REGIONS:
        path = MODEL_PREFIX / region / "Model_Outputs" / f"BASE_{RC}" / "ParameterTable.csv"

        try:
            df_head = pd.read_csv(path, nrows=5)
        except Exception:
            df_head = pd.read_csv(path, nrows=5, engine="python", on_bad_lines="skip")

        cols = list(df_head.columns)
        param_col = next((c for c in cols if str(c).strip().upper() == "PARAMETER"), None)
        value_col = next((c for c in cols if str(c).strip().upper() == "VALUE"), None)

        if param_col is None or value_col is None:
            raise KeyError(
                f"[{region}] Could not find PARAMETER/VALUE columns in {path}. "
                f"Available columns: {cols}"
            )

        try:
            df = pd.read_csv(path, usecols=[param_col, value_col])
        except Exception:
            df = pd.read_csv(
                path,
                usecols=[param_col, value_col],
                engine="python",
                on_bad_lines="skip",
            )

        df = df.rename(columns={param_col: "PARAMETER", value_col: "VALUE"})
        tables[region] = df
        print(f"[{region}] parameter loaded: {df.shape}")

    return tables


def load_climate_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for region in REGIONS:
        path = MODEL_PREFIX / region / "Model_Outputs" / f"BASE_{RC}" / "climateTable.csv"
        tables[region] = load_csv_with_fallback(path)
        print(f"[{region}] climate loaded: {tables[region].shape}")
    return tables


def load_lut_tables() -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for region in REGIONS:
        path = get_reg_link_path(region)
        tables[region] = load_csv_with_fallback(path)
        print(f"[{region}] LUT loaded: {tables[region].shape} | {path}")
    return tables


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    print("\n=== Loading inputs ===")

    fu_tables = load_fu_area_tables()
    param_tables = load_parameter_tables()
    climate_tables = load_climate_tables()
    lut_tables = load_lut_tables()

    # =====================================================
    # LAND USE + STREAM
    # =====================================================

    print("\n=== Building land use + stream summary ===")

    landuse_stream_df = build_land_use_stream_summary(
        fu_area_tables_by_region=fu_tables,
        parameter_tables_by_region=param_tables,
        region_order=REGIONS,
    )

    landuse_stream_out = OUTPUT_PATH / "landuse_stream_summary.csv"
    landuse_stream_df.to_csv(landuse_stream_out)
    print(f"Saved → {landuse_stream_out}")

    # =====================================================
    # DETAILED LAND USE
    # =====================================================

    print("\n=== Building detailed land use summaries ===")

    landuse_results = build_land_use_detailed_summary_across_regions(
        fu_area_tables_by_region=fu_tables,
        reg_lut_tables_by_region=lut_tables,
        region_order=REGIONS,
        fus_of_interest=FUS_OF_INTEREST,
    )

    out_landuse_all = OUTPUT_PATH / f"LandUse_AllRows_{RC}.csv"
    out_subcat_fu = OUTPUT_PATH / f"Subcat_FU_Area_{RC}.csv"
    out_mu48_fu_long = OUTPUT_PATH / f"MU48_FU_AreaPct_long_{RC}.csv"
    out_mu48_area_wide = OUTPUT_PATH / f"MU48_FU_Area_ha_wide_{RC}.csv"
    out_mu48_pct_wide = OUTPUT_PATH / f"MU48_FU_Percent_wide_{RC}.csv"
    out_region_fu = OUTPUT_PATH / f"Region_FU_AreaPct_long_{RC}.csv"
    out_landuse_qa = OUTPUT_PATH / f"QA_LandUse_CheckSummary_{RC}.csv"

    landuse_results["fu_area_all"].to_csv(out_landuse_all, index=False)
    landuse_results["subcat_fu"].to_csv(out_subcat_fu, index=False)
    landuse_results["mu48_fu"].to_csv(out_mu48_fu_long, index=False)
    landuse_results["mu48_area_wide"].to_csv(out_mu48_area_wide, index=False)
    landuse_results["mu48_pct_wide"].to_csv(out_mu48_pct_wide, index=False)
    landuse_results["region_fu"].to_csv(out_region_fu, index=False)
    landuse_results["qa_summary"].to_csv(out_landuse_qa, index=False)

    # =====================================================
    # RAINFALL
    # =====================================================

    print("\n=== Building rainfall summaries ===")

    rainfall_results = build_rainfall_summary_across_regions(
        climate_tables_by_region=climate_tables,
        fu_area_tables_by_region=fu_tables,
        reg_lut_tables_by_region=lut_tables,
        region_order=REGIONS,
        n_years=N_YEARS,
    )

    print("\n=== Exporting rainfall outputs ===")

    out_subcat_rain = OUTPUT_PATH / f"AnnualRainfall_Subcat_{RC}.csv"
    out_basin35_rain = OUTPUT_PATH / f"AnnualRainfall_35Basins_{RC}.csv"
    out_region_rain = OUTPUT_PATH / f"AnnualRainfall_6Regions_{RC}.csv"
    out_mu48_rain = OUTPUT_PATH / f"AnnualRainfall_Manag_Unit_48_{RC}.csv"
    out_gbr_rain = OUTPUT_PATH / f"AnnualRainfall_GBR_{RC}.csv"
    out_rain_qa = OUTPUT_PATH / f"QA_RainfallSummary_{RC}.csv"

    rainfall_results["subcat"].to_csv(out_subcat_rain, index=False)
    rainfall_results["basin35"].to_csv(out_basin35_rain, index=False)
    rainfall_results["region"].to_csv(out_region_rain, index=False)
    rainfall_results["mu48"].to_csv(out_mu48_rain, index=False)
    rainfall_results["gbr"].to_csv(out_gbr_rain, index=False)
    rainfall_results["qa_summary"].to_csv(out_rain_qa, index=False)

    print("\nSaved files:")
    print(landuse_stream_out)
    print(out_landuse_all)
    print(out_subcat_fu)
    print(out_mu48_fu_long)
    print(out_mu48_area_wide)
    print(out_mu48_pct_wide)
    print(out_region_fu)
    print(out_landuse_qa)
    print(out_subcat_rain)
    print(out_basin35_rain)
    print(out_region_rain)
    print(out_mu48_rain)
    print(out_gbr_rain)
    print(out_rain_qa)

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()