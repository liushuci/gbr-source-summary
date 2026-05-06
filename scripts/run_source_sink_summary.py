from __future__ import annotations

from pathlib import Path
import logging
import pandas as pd

from gbr_source_summary.workflows_source_sink import (
    summarise_basin_budget_for_constituent,
    build_basin_source_sink_summary_from_raw,
    build_region_source_sink_summary,
    build_gbr_source_sink_summary,
    convert_source_sink_to_annual_units,
    build_basin_export_summary_from_contributor,
    append_export_groups,
)
from gbr_source_summary.naming import standardise_constituent_names
from gbr_source_summary.io import load_reg_contributor_data_grid_with_lut
from gbr_source_summary.config import GBRConfig

# =========================================================
# CONFIG
# =========================================================

BASE_PATH = Path(r"F:/RC13_RC2023_24_Gold")
RESULTS_PATH = BASE_PATH / "Gold_ResultsSets_PointOfTruth"
REGION_DEF_PATH = BASE_PATH / "Regions"

REGIONS = ["CY", "WT", "BU", "MW", "FI", "BM"]
SCENARIO = "BASE"
RC = "Gold_93_23"

MODEL_YEARS = 30.0
VALUE_COLUMN = "Total_Load_in_Kg"
EXPORT_VALUE_COLUMN = "LoadToRegExport (kg)"

OUTPUT_DIR = BASE_PATH / "report_card_summary" / "source_sink"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCE_SINK_CONSTITUENTS = ["FS", "CS", "PN", "PP", "DIN", "DON", "DIP", "DOP"]

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =========================================================
# HELPERS
# =========================================================

def get_raw_results_path(region: str) -> Path:
    return (
        RESULTS_PATH
        / region
        / "Model_Outputs"
        / f"{SCENARIO}_{RC}"
        / "RawResults.csv"
    )


def get_reg_link_path(region: str) -> Path:
    return REGION_DEF_PATH / f"{region}_Reg_cat_node_link.csv"


def load_and_prepare_raw(region: str) -> pd.DataFrame:
    logger.info(f"Loading {region}")

    raw = pd.read_csv(get_raw_results_path(region))
    reg_link = pd.read_csv(get_reg_link_path(region))

    raw.columns = [str(c).strip().replace("\ufeff", "") for c in raw.columns]
    reg_link.columns = [str(c).strip().replace("\ufeff", "") for c in reg_link.columns]

    logger.info(f"{region} raw columns     : {list(raw.columns[:10])}")
    logger.info(f"{region} reg_link columns: {list(reg_link.columns)}")

    rename_map = {}
    for col in reg_link.columns:
        col_upper = col.upper()
        if col_upper in {"MODELELEMENT", "MODEL_ELEMENT"}:
            rename_map[col] = "ModelElement"
        elif col_upper == "MANAG_UNIT_48":
            rename_map[col] = "Manag_Unit_48"
        elif col_upper == "BASIN_35":
            rename_map[col] = "Basin_35"

    reg_link = reg_link.rename(columns=rename_map)

    if "ModelElement" not in raw.columns:
        raise KeyError(f"{region}: missing 'ModelElement' in raw columns: {list(raw.columns)}")

    if "ModelElement" not in reg_link.columns:
        raise KeyError(f"{region}: missing 'ModelElement' in reg_link columns: {list(reg_link.columns)}")

    required_lut_cols = ["Manag_Unit_48", "Basin_35"]
    missing_lut = [c for c in required_lut_cols if c not in reg_link.columns]
    if missing_lut:
        raise KeyError(f"{region}: missing LUT columns {missing_lut} in reg_link columns: {list(reg_link.columns)}")

    raw["ModelElement"] = raw["ModelElement"].astype(str).str.strip()
    reg_link["ModelElement"] = reg_link["ModelElement"].astype(str).str.strip()

    reg_link = reg_link[["ModelElement", "Manag_Unit_48", "Basin_35"]].drop_duplicates()

    raw = pd.merge(raw, reg_link, on="ModelElement", how="left")

    missing_mu = raw["Manag_Unit_48"].isna().sum()
    missing_b35 = raw["Basin_35"].isna().sum()
    total = len(raw)

    logger.info(f"{region}: missing MU48   = {missing_mu}/{total} ({missing_mu/total:.2%})")
    logger.info(f"{region}: missing Basin35 = {missing_b35}/{total} ({missing_b35/total:.2%})")

    missing_df = (
        raw.loc[
            raw["Manag_Unit_48"].isna() | raw["Basin_35"].isna(),
            ["ModelElement", "Manag_Unit_48", "Basin_35"],
        ]
        .drop_duplicates()
        .sort_values("ModelElement")
    )

    output_path = OUTPUT_DIR / f"missing_model_elements_{region}.csv"
    missing_df.to_csv(output_path, index=False)
    logger.info(f"Saved missing elements -> {output_path}")

    return raw


def build_subcat_source_sink_summary_from_raw(
    raw_results: pd.DataFrame,
    region: str,
    scenario: str,
    subcat_column: str = "ModelElement",
    constituent_column: str = "Constituent",
    budget_element_column: str = "BudgetElement",
    value_column: str = VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Build subcatchment source-sink summary directly from raw results.

    Returns long-format dataframe:
    - Region
    - Scenario
    - Subcatchment
    - Manag_Unit_48
    - Basin_35
    - Constituent
    - BudgetGroup
    - Total_Load_in_Kg
    - Units
    """
    required = [
        subcat_column,
        constituent_column,
        budget_element_column,
        value_column,
        "Manag_Unit_48",
        "Basin_35",
    ]
    missing = [c for c in required if c not in raw_results.columns]
    if missing:
        raise KeyError(f"Missing required columns in raw_results: {missing}")

    work = raw_results.rename(
        columns={
            subcat_column: "Subcatchment",
            constituent_column: "Constituent",
            budget_element_column: "BudgetElement",
            value_column: VALUE_COLUMN,
        }
    ).copy()

    work["Constituent"] = standardise_constituent_names(work["Constituent"])
    work[VALUE_COLUMN] = pd.to_numeric(work[VALUE_COLUMN], errors="coerce").fillna(0.0)

    work = work.loc[work["Subcatchment"].notna()].copy()
    work["Subcatchment"] = work["Subcatchment"].astype(str).str.strip()
    work["Manag_Unit_48"] = work["Manag_Unit_48"].astype(str).str.strip()
    work["Basin_35"] = work["Basin_35"].astype(str).str.strip()

    work = work.loc[work["Constituent"].isin(SOURCE_SINK_CONSTITUENTS)].copy()

    hillslope_variants = {
        "Hillslope surface soil",
        "Hillslope sub-surface soil",
        "Hillslope no source distinction",
    }
    work.loc[work["BudgetElement"].isin(hillslope_variants), "BudgetElement"] = "Hillslope"

    rows: list[pd.DataFrame] = []

    grouped = work.groupby(
        ["Subcatchment", "Constituent", "Manag_Unit_48", "Basin_35"],
        dropna=False,
    )

    for (subcat, constituent, mu48, basin35), df_sc in grouped:
        summary = summarise_basin_budget_for_constituent(
            df_basin_constituent=df_sc[["BudgetElement", VALUE_COLUMN]].copy(),
            constituent=str(constituent),
            region=region,
        )

        if summary.empty:
            continue

        summary["Region"] = region
        summary["Scenario"] = scenario
        summary["Subcatchment"] = subcat
        summary["Manag_Unit_48"] = mu48
        summary["Basin_35"] = basin35
        summary["Units"] = "kg"
        rows.append(summary)

    if not rows:
        return pd.DataFrame(
            columns=[
                "Region",
                "Scenario",
                "Subcatchment",
                "Manag_Unit_48",
                "Basin_35",
                "Constituent",
                "BudgetGroup",
                VALUE_COLUMN,
                "Units",
            ]
        )

    out = pd.concat(rows, ignore_index=True)
    out = out[
        [
            "Region",
            "Scenario",
            "Subcatchment",
            "Manag_Unit_48",
            "Basin_35",
            "Constituent",
            "BudgetGroup",
            VALUE_COLUMN,
            "Units",
        ]
    ]

    out = out.sort_values(
        ["Region", "Subcatchment", "Constituent", "BudgetGroup"]
    ).reset_index(drop=True)

    return out


def load_and_prepare_contributor(cfg: GBRConfig, region: str) -> pd.DataFrame:
    """
    Load RegContributorDataGrid with LUT already joined.
    """
    contrib = load_reg_contributor_data_grid_with_lut(cfg, region, SCENARIO).copy()
    contrib.columns = [str(c).strip().replace("\ufeff", "") for c in contrib.columns]

    required = ["Constituent", "Process", EXPORT_VALUE_COLUMN, "Manag_Unit_48", "Basin_35"]
    missing = [c for c in required if c not in contrib.columns]
    if missing:
        raise KeyError(f"{region}: missing contributor columns {missing}")

    contrib["Constituent"] = standardise_constituent_names(contrib["Constituent"])
    contrib[EXPORT_VALUE_COLUMN] = pd.to_numeric(contrib[EXPORT_VALUE_COLUMN], errors="coerce").fillna(0.0)
    contrib["Manag_Unit_48"] = contrib["Manag_Unit_48"].astype(str).str.strip()
    contrib["Basin_35"] = contrib["Basin_35"].astype(str).str.strip()

    return contrib


def add_percent_contribution(
    df: pd.DataFrame,
    group_cols: list[str],
    value_column: str = VALUE_COLUMN,
    pct_col: str = "PercentOfGroup",
) -> pd.DataFrame:
    """
    Add percent contribution of each row within a group.
    """
    out = df.copy()
    out[value_column] = pd.to_numeric(out[value_column], errors="coerce").fillna(0.0)

    totals = out.groupby(group_cols, dropna=False)[value_column].transform("sum")
    out[pct_col] = 0.0
    mask = totals != 0
    out.loc[mask, pct_col] = out.loc[mask, value_column] / totals[mask] * 100.0

    return out


def build_sankey_pivot(
    df: pd.DataFrame,
    index_cols: list[str],
    value_column: str = VALUE_COLUMN,
) -> pd.DataFrame:
    """
    Pivot BudgetGroup to wide columns for convenience / checking.
    """
    out = (
        df.pivot_table(
            index=index_cols,
            columns="BudgetGroup",
            values=value_column,
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )

    out.columns.name = None
    return out


def qa_check_subcat_to_group(
    subcat_df: pd.DataFrame,
    group_col: str,
    compare_df: pd.DataFrame,
    compare_name: str,
    value_column: str = VALUE_COLUMN,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """
    QA check that subcatchment source-sink aggregates to target group totals.
    """
    subcat_agg = (
        subcat_df.groupby(
            ["Region", "Scenario", group_col, "Constituent", "BudgetGroup", "Units"],
            dropna=False,
            as_index=False,
        )[value_column]
        .sum()
        .rename(columns={group_col: compare_name, value_column: "SubcatAggregated"})
    )

    compare_cols = ["Region", "Scenario", compare_name, "Constituent", "BudgetGroup", "Units", value_column]
    missing = [c for c in compare_cols if c not in compare_df.columns]
    if missing:
        raise KeyError(f"Missing columns in compare_df for QA: {missing}")

    target = compare_df[compare_cols].rename(columns={value_column: "TargetValue"})

    qa = pd.merge(
        subcat_agg,
        target,
        on=["Region", "Scenario", compare_name, "Constituent", "BudgetGroup", "Units"],
        how="outer",
    )

    qa["SubcatAggregated"] = pd.to_numeric(qa["SubcatAggregated"], errors="coerce").fillna(0.0)
    qa["TargetValue"] = pd.to_numeric(qa["TargetValue"], errors="coerce").fillna(0.0)
    qa["Difference"] = qa["SubcatAggregated"] - qa["TargetValue"]
    qa["WithinTolerance"] = qa["Difference"].abs() <= tol

    return qa.sort_values(
        ["Region", "Scenario", compare_name, "Constituent", "BudgetGroup"]
    ).reset_index(drop=True)


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    cfg = GBRConfig(main_path=BASE_PATH)

    subcat_all = []
    basin_mu48_all = []
    basin35_all = []

    for region in REGIONS:
        # ---------------------------------------------
        # Budget-based source/sink
        # ---------------------------------------------
        raw = load_and_prepare_raw(region)

        subcat_df = build_subcat_source_sink_summary_from_raw(
            raw_results=raw,
            region=region,
            scenario=SCENARIO,
            subcat_column="ModelElement",
            constituent_column="Constituent",
            budget_element_column="BudgetElement",
            value_column=VALUE_COLUMN,
        )

        basin_mu48_budget = build_basin_source_sink_summary_from_raw(
            raw_results=raw,
            region=region,
            scenario=SCENARIO,
            basin_column="Manag_Unit_48",
            constituent_column="Constituent",
            budget_element_column="BudgetElement",
            value_column=VALUE_COLUMN,
        )

        # Basin35 budget summary from subcatchment summary
        basin35_budget = (
            subcat_df.groupby(
                ["Region", "Scenario", "Basin_35", "Constituent", "BudgetGroup", "Units"],
                dropna=False,
                as_index=False,
            )[VALUE_COLUMN]
            .sum()
            .rename(columns={"Basin_35": "Basin"})
        )

        # ---------------------------------------------
        # Export-based grouped summaries
        # ---------------------------------------------
        contrib = load_and_prepare_contributor(cfg, region)

        basin_mu48_export = build_basin_export_summary_from_contributor(
            export_results=contrib,
            region=region,
            scenario=SCENARIO,
            basin_column="Manag_Unit_48",
            constituent_column="Constituent",
            process_column="Process",
            value_column=EXPORT_VALUE_COLUMN,
        )

        basin35_export = build_basin_export_summary_from_contributor(
            export_results=contrib,
            region=region,
            scenario=SCENARIO,
            basin_column="Basin_35",
            constituent_column="Constituent",
            process_column="Process",
            value_column=EXPORT_VALUE_COLUMN,
        )

        # ---------------------------------------------
        # Append export groups into summary tables
        # ---------------------------------------------
        basin_mu48_full = append_export_groups(
            source_sink_df=basin_mu48_budget,
            export_df=basin_mu48_export,
            spatial_cols=["Region", "Scenario", "Basin"],
            constituent_col="Constituent",
            value_column=VALUE_COLUMN,
        )

        basin35_full = append_export_groups(
            source_sink_df=basin35_budget,
            export_df=basin35_export,
            spatial_cols=["Region", "Scenario", "Basin"],
            constituent_col="Constituent",
            value_column=VALUE_COLUMN,
        )

        # Subcatchment table kept as budget summary only for now
        subcat_all.append(subcat_df)
        basin_mu48_all.append(basin_mu48_full)
        basin35_all.append(basin35_full)

    subcat_all = pd.concat(subcat_all, ignore_index=True)
    basin_all = pd.concat(basin_mu48_all, ignore_index=True)
    basin35_df = pd.concat(basin35_all, ignore_index=True)

    region_df = build_region_source_sink_summary(
        basin_source_sink=basin_all,
        scenario=SCENARIO,
        value_column=VALUE_COLUMN,
    )

    gbr_df = build_gbr_source_sink_summary(
        region_source_sink=region_df,
        value_column=VALUE_COLUMN,
    )

    # Convert to annual units
    subcat_all = convert_source_sink_to_annual_units(
        subcat_all,
        model_years=MODEL_YEARS,
        value_column=VALUE_COLUMN,
    )

    basin_all = convert_source_sink_to_annual_units(
        basin_all,
        model_years=MODEL_YEARS,
        value_column=VALUE_COLUMN,
    )

    basin35_df = convert_source_sink_to_annual_units(
        basin35_df,
        model_years=MODEL_YEARS,
        value_column=VALUE_COLUMN,
    )

    region_df = convert_source_sink_to_annual_units(
        region_df,
        model_years=MODEL_YEARS,
        value_column=VALUE_COLUMN,
    )

    gbr_df = convert_source_sink_to_annual_units(
        gbr_df,
        model_years=MODEL_YEARS,
        value_column=VALUE_COLUMN,
    )

    # Add percentage columns
    subcat_all = add_percent_contribution(
        subcat_all,
        group_cols=["Region", "Scenario", "Subcatchment", "Constituent"],
        value_column=VALUE_COLUMN,
        pct_col="PercentOfSubcatchmentConstituent",
    )

    basin_all = add_percent_contribution(
        basin_all,
        group_cols=["Region", "Scenario", "Basin", "Constituent"],
        value_column=VALUE_COLUMN,
        pct_col="PercentOfMU48Constituent",
    )

    basin35_df = add_percent_contribution(
        basin35_df,
        group_cols=["Region", "Scenario", "Basin", "Constituent"],
        value_column=VALUE_COLUMN,
        pct_col="PercentOfBasin35Constituent",
    )

    region_df = add_percent_contribution(
        region_df,
        group_cols=["Region", "Scenario", "Constituent"],
        value_column=VALUE_COLUMN,
        pct_col="PercentOfRegionConstituent",
    )

    gbr_df = add_percent_contribution(
        gbr_df,
        group_cols=["Scenario", "Constituent"],
        value_column=VALUE_COLUMN,
        pct_col="PercentOfGBRConstituent",
    )

    # QA checks
    # subcat -> MU48 only checks budget groups that exist in both tables
    qa_subcat_to_mu48 = qa_check_subcat_to_group(
        subcat_df=subcat_all,
        group_col="Manag_Unit_48",
        compare_df=basin_all.loc[~basin_all["BudgetGroup"].str.endswith("Export", na=False)].copy(),
        compare_name="Basin",
        value_column=VALUE_COLUMN,
        tol=1e-6,
    )

    qa_subcat_to_basin35 = qa_check_subcat_to_group(
        subcat_df=subcat_all,
        group_col="Basin_35",
        compare_df=basin35_df.loc[~basin35_df["BudgetGroup"].str.endswith("Export", na=False)].copy(),
        compare_name="Basin",
        value_column=VALUE_COLUMN,
        tol=1e-6,
    )

    # Wide pivots for convenience / checking
    sankey_subcat_wide = build_sankey_pivot(
        subcat_all,
        index_cols=["Region", "Scenario", "Subcatchment", "Manag_Unit_48", "Basin_35", "Constituent", "Units"],
        value_column=VALUE_COLUMN,
    )

    sankey_mu48_wide = build_sankey_pivot(
        basin_all,
        index_cols=["Region", "Scenario", "Basin", "Constituent", "Units"],
        value_column=VALUE_COLUMN,
    )

    sankey_basin35_wide = build_sankey_pivot(
        basin35_df,
        index_cols=["Region", "Scenario", "Basin", "Constituent", "Units"],
        value_column=VALUE_COLUMN,
    )

    sankey_region_wide = build_sankey_pivot(
        region_df,
        index_cols=["Region", "Scenario", "Constituent", "Units"],
        value_column=VALUE_COLUMN,
    )

    sankey_gbr_wide = build_sankey_pivot(
        gbr_df,
        index_cols=["Scenario", "Constituent", "Units"],
        value_column=VALUE_COLUMN,
    )

    # Save outputs
    subcat_all.to_csv(OUTPUT_DIR / "subcat_source_sink.csv", index=False)
    basin_all.to_csv(OUTPUT_DIR / "mu48_source_sink.csv", index=False)
    basin35_df.to_csv(OUTPUT_DIR / "basin35_source_sink.csv", index=False)
    region_df.to_csv(OUTPUT_DIR / "region_source_sink.csv", index=False)
    gbr_df.to_csv(OUTPUT_DIR / "gbr_source_sink.csv", index=False)

    qa_subcat_to_mu48.to_csv(OUTPUT_DIR / "qa_subcat_to_mu48_check.csv", index=False)
    qa_subcat_to_basin35.to_csv(OUTPUT_DIR / "qa_subcat_to_basin35_check.csv", index=False)

    sankey_subcat_wide.to_csv(OUTPUT_DIR / "subcat_source_sink_sankey_wide.csv", index=False)
    sankey_mu48_wide.to_csv(OUTPUT_DIR / "mu48_source_sink_sankey_wide.csv", index=False)
    sankey_basin35_wide.to_csv(OUTPUT_DIR / "basin35_source_sink_sankey_wide.csv", index=False)
    sankey_region_wide.to_csv(OUTPUT_DIR / "region_source_sink_sankey_wide.csv", index=False)
    sankey_gbr_wide.to_csv(OUTPUT_DIR / "gbr_source_sink_sankey_wide.csv", index=False)

    logger.info("Source-sink summary complete")
    logger.info(f"Saved: {OUTPUT_DIR / 'subcat_source_sink.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'mu48_source_sink.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'basin35_source_sink.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'region_source_sink.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'gbr_source_sink.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'qa_subcat_to_mu48_check.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'qa_subcat_to_basin35_check.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'subcat_source_sink_sankey_wide.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'mu48_source_sink_sankey_wide.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'basin35_source_sink_sankey_wide.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'region_source_sink_sankey_wide.csv'}")
    logger.info(f"Saved: {OUTPUT_DIR / 'gbr_source_sink_sankey_wide.csv'}")

    logger.info(
        f"QA subcat->MU48 failures: {(~qa_subcat_to_mu48['WithinTolerance']).sum()}"
    )
    logger.info(
        f"QA subcat->Basin35 failures: {(~qa_subcat_to_basin35['WithinTolerance']).sum()}"
    )


if __name__ == "__main__":
    main()