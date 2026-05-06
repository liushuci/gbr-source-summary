"""
Run FU load and areal load summaries for GBR RC13 workflow.

Outputs:
- Annual FU load summary tables for:
    - FS
    - DIN
    - PN
    - PP
- Areal FU load summary tables for:
    - FS
    - DIN
    - PN
    - PP
- GBR FU contribution pie charts
- Regional tonnage vs areal-load dual-axis bar charts
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.workflows_fu import build_fu_export_summaries

# =========================================================
# CONFIG
# =========================================================

RC = "Gold_93_23"
REGIONS = ["CY", "WT", "BU", "MW", "FI", "BM"]
SCENARIO = "BASE"
CONSTITUENTS = ["FS", "DIN", "PN", "PP"]

MAIN_PATH = Path(r"F:\RC13_RC2023_24_Gold")
OUTPUT_PATH = MAIN_PATH / "report_card_summary" / "fu_load_summary"
LANDUSE_PATH = MAIN_PATH / "report_card_summary" / "landuse_rainfall" / "landuse_stream_summary.csv"

OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

# =========================================================
# HELPERS
# =========================================================

REGION_NAME_MAP = {
    "CY": "Cape York",
    "WT": "Wet Tropics",
    "BU": "Burdekin",
    "MW": "Mackay Whitsunday",
    "FI": "Fitzroy",
    "BM": "Burnett Mary",
}

FU_ORDER = [
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


def load_landuse_stream_summary(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Land use stream summary not found: {path}\n"
            f"Run scripts/run_landuse_rainfall_summary.py first."
        )

    df = pd.read_csv(path, index_col=0)
    print(f"Loaded landuse stream summary: {df.shape} | {path}")
    return df


def standardise_fu_names_in_series(s: pd.Series) -> pd.Series:
    """
    Match FU naming/order to the legacy report-card output table.
    """
    s = s.copy()
    s.index = s.index.astype(str)

    if "Dryland Cropping" in s.index or "Irrigated Cropping" in s.index:
        s["Cropping"] = s.get("Dryland Cropping", 0) + s.get("Irrigated Cropping", 0)

    if "Urban + Other" not in s.index:
        s["Urban + Other"] = s.get("Urban", 0) + s.get("Other", 0)

    for fu in FU_ORDER:
        if fu not in s.index:
            s[fu] = 0.0

    return s[FU_ORDER]


def _extract_fu_series_from_wide_summary(
    df: pd.DataFrame,
    constituent: str,
) -> pd.Series:
    """
    Extract one constituent series from a wide FU summary table.

    Supported shapes:
    1. FU as index, constituent as column
    2. FU as a normal column, constituent as column
    """
    if constituent not in df.columns:
        raise KeyError(
            f"Constituent '{constituent}' not found. Available columns: {list(df.columns)}"
        )

    if "FU" in df.columns:
        s = df.set_index("FU")[constituent].copy()
    else:
        s = df[constituent].copy()
        s.index = df.index

    s = pd.to_numeric(s, errors="coerce")
    return s


def build_fu_load_summary_from_region_summaries(
    region_summaries_by_region: dict[str, pd.DataFrame],
    combined_summary: pd.DataFrame,
    constituents: list[str],
    region_order: list[str],
    model_years: int,
) -> dict[str, pd.DataFrame]:
    """
    Build legacy-style FU load summary tables from workflows_fu outputs.

    Expects region summaries and combined summary in wide format:
    - rows = FU
    - columns include constituents such as FS, DIN, PN, PP

    Assumes values are total loads in kg over the full model period.
    Converts to average annual:
    - FS -> kt/year
    - DIN/PN/PP -> t/year
    """
    results: dict[str, pd.DataFrame] = {}
    per_year = 1.0 / model_years

    for con in constituents:
        rows = []

        for region in region_order:
            df = region_summaries_by_region[region]
            s = _extract_fu_series_from_wide_summary(df, con)
            s = standardise_fu_names_in_series(s)

            if con == "FS":
                s = s * 1e-6 * per_year   # kg -> kt/year
            else:
                s = s * 1e-3 * per_year   # kg -> t/year

            s.name = REGION_NAME_MAP.get(region, region)
            rows.append(s)

        gbr_series = _extract_fu_series_from_wide_summary(combined_summary, con)
        gbr_series = standardise_fu_names_in_series(gbr_series)

        if con == "FS":
            gbr_series = gbr_series * 1e-6 * per_year
        else:
            gbr_series = gbr_series * 1e-3 * per_year

        gbr_series.name = "GBR"
        rows.append(gbr_series)

        out = pd.DataFrame(rows).fillna(0).round(2)

        if con == "FS":
            out.columns = [
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
            out.columns = [
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

        results[con] = out

    return results


def build_fu_areal_load_summary(
    fu_load_summary: dict[str, pd.DataFrame],
    fu_area_summary: pd.DataFrame,
    constituents: list[str],
) -> dict[str, pd.DataFrame]:
    """
    Convert annual FU loads to areal loads using landuse_stream_summary.csv
    as denominator.

    For FS:
    - kt/year -> t/year, then divide by ha
    - Stream column uses km denominator

    For DIN/PN/PP:
    - t/year -> kg/year, then divide by ha
    - Stream column uses km denominator
    """
    results: dict[str, pd.DataFrame] = {}

    area_values = fu_area_summary.values.astype(float)

    for con in constituents:
        load_df = fu_load_summary[con].copy()
        load_values = load_df.values.astype(float)

        with np.errstate(divide="ignore", invalid="ignore"):
            areal_values = (load_values * 1000.0) / area_values

        areal_values = np.where(np.isfinite(areal_values), areal_values, 0.0)

        out = pd.DataFrame(
            areal_values,
            index=load_df.index,
            columns=load_df.columns,
        ).round(3)

        if con == "FS":
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


def plot_gbr_export_contribution_pies(
    fu_load_summary: dict[str, pd.DataFrame],
    constituents: list[str],
    output_dir: Path,
) -> None:
    """
    Create GBR export contribution pie charts by FU.
    Excludes Stream to match the legacy logic.
    """
    plot_dir = output_dir / "variousExports"
    plot_dir.mkdir(parents=True, exist_ok=True)

    for con in constituents:
        summary_export_gbr = fu_load_summary[con].loc["GBR"].copy()

        # drop Stream only
        if "Stream (kt/year)" in summary_export_gbr.index:
            summary_export_gbr = summary_export_gbr.drop("Stream (kt/year)")
        elif "Stream (t/year)" in summary_export_gbr.index:
            summary_export_gbr = summary_export_gbr.drop("Stream (t/year)")

        fig, ax = plt.subplots(figsize=(8, 8))

        summary_export_gbr.plot.pie(
            ax=ax,
            autopct="%1.1f%%",
            labels=None,
            fontsize=0,
            pctdistance=0.1,
            radius=1.1,
            wedgeprops={"edgecolor": "k", "linewidth": 1},
        )

        total = summary_export_gbr.values.sum()
        if total == 0:
            labels = [f"{name} - 0.0 %" for name in summary_export_gbr.index]
        else:
            percent = 100.0 * summary_export_gbr.values / total
            labels = [f"{name} - {pct:.1f} %" for name, pct in zip(summary_export_gbr.index, percent)]

        ax.legend(labels, bbox_to_anchor=(0.95, 0.61), ncol=1, fontsize=12)
        ax.set_ylabel("")

        out_path = plot_dir / f"exportContributionGBR_{con}.png"
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

        print(out_path)


def plot_fu_tonnage_vs_areal_by_region(
    fu_load_summary: dict[str, pd.DataFrame],
    fu_areal_load_summary: dict[str, pd.DataFrame],
    output_dir: Path,
) -> None:
    """
    Create dual-axis bar charts comparing regional total export load and
    areal export load for selected FU/constituent combinations.

    Styled to match the legacy report-card charts more closely.

    Plots created:
    - Grazing: FS
    - Stream: FS
    - Sugarcane: DIN
    """
    plot_dir = output_dir / "variousExports"
    plot_dir.mkdir(parents=True, exist_ok=True)

    plot_specs = [
        {
            "fu": "Grazing",
            "constituent": "FS",
            "load_col": "Grazing (kt/year)",
            "areal_col": "Grazing (t/ha/year)",
            "left_ylabel": "FS (kt/yr)",
            "right_ylabel": "FS (t/ha/yr)",
            "left_legend": "kt/yr",
            "right_legend": "t/ha/yr",
            "include_gbr": False,
        },
        {
            "fu": "Stream",
            "constituent": "FS",
            "load_col": "Stream (kt/year)",
            "areal_col": "Stream (t/km/year)",
            "left_ylabel": "FS (kt/yr)",
            "right_ylabel": "FS (t/km/yr)",
            "left_legend": "kt/yr",
            "right_legend": "t/km/yr",
            "include_gbr": True,
        },
        {
            "fu": "Sugarcane",
            "constituent": "DIN",
            "load_col": "Sugracane (t/year)",
            "areal_col": "Sugracane (kg/ha/year)",
            "left_ylabel": "DIN (t/yr)",
            "right_ylabel": "DIN (kg/ha/yr)",
            "left_legend": "t/yr",
            "right_legend": "kg/ha/yr",
            "include_gbr": True,
        },
    ]

    for spec in plot_specs:
        con = spec["constituent"]
        fu = spec["fu"]

        load_df = fu_load_summary[con]
        areal_df = fu_areal_load_summary[con]

        if spec["load_col"] not in load_df.columns:
            raise KeyError(
                f"Missing load column '{spec['load_col']}' for {con}. "
                f"Available: {list(load_df.columns)}"
            )
        if spec["areal_col"] not in areal_df.columns:
            raise KeyError(
                f"Missing areal column '{spec['areal_col']}' for {con}. "
                f"Available: {list(areal_df.columns)}"
            )

        if spec["include_gbr"]:
            total_series = load_df[spec["load_col"]].copy()
            areal_series = areal_df[spec["areal_col"]].copy()
        else:
            total_series = load_df.loc[load_df.index != "GBR", spec["load_col"]].copy()
            areal_series = areal_df.loc[areal_df.index != "GBR", spec["areal_col"]].copy()

        total_series = total_series.astype(float)
        areal_series = areal_series.astype(float)

        x = np.arange(len(total_series))

        fig, ax1 = plt.subplots(figsize=(6.4, 4.8))

        # --- WIDE pink bar (background) ---
        ax1.bar(
            x,
            total_series.values,
            width=0.35,
            color="m",
            edgecolor="black",
            label=spec["left_legend"],
            zorder=1,
        )

        ax1.set_ylabel(spec["left_ylabel"], size=8)
        ax1.set_xticks(x)
        ax1.set_xticklabels(total_series.index, rotation=90)
        ax1.grid(False)

        # --- THIN green bar (overlay, looks stacked visually) ---
        ax2 = ax1.twinx()

        ax2.bar(
            x,
            areal_series.values,
            width=0.18,
            color="g",
            edgecolor="black",
            label=spec["right_legend"],
            zorder=2,
        )

        ax2.set_ylabel(spec["right_ylabel"], size=8)
        ax2.grid(False)

        ax1.legend(
            [spec["left_legend"]],
            loc="lower left",
            bbox_to_anchor=(0.0, 1.01),
            fontsize=8,
            frameon=True,
        )
        ax2.legend(
            [spec["right_legend"]],
            loc="lower left",
            bbox_to_anchor=(0.18, 1.01),
            fontsize=8,
            frameon=True,
        )

        plt.tight_layout()

        out_path = plot_dir / f"{con}_exportTonnageArealGBR_{fu}.png"
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

        print(out_path)


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    print("\n=== Loading land use denominator table ===")
    fu_area_summary = load_landuse_stream_summary(LANDUSE_PATH)

    print("\n=== Building FU export summaries from package workflow ===")
    print(type(MAIN_PATH), MAIN_PATH)

    cfg = GBRConfig(main_path=MAIN_PATH, rc=RC)

    _, region_summaries_by_region, combined_summary = build_fu_export_summaries(
        cfg=cfg,
        model=SCENARIO,
        regions=REGIONS,
        constituents=CONSTITUENTS,
        units="kg",
        basin_scale="48",
    )

    print("\n=== Building FU total load summaries ===")
    fu_load_summary = build_fu_load_summary_from_region_summaries(
        region_summaries_by_region=region_summaries_by_region,
        combined_summary=combined_summary,
        constituents=CONSTITUENTS,
        region_order=REGIONS,
        model_years=cfg.model_years,
    )

    print("\n=== Building FU areal load summaries ===")
    fu_areal_load_summary = build_fu_areal_load_summary(
        fu_load_summary=fu_load_summary,
        fu_area_summary=fu_area_summary,
        constituents=CONSTITUENTS,
    )

    print("\n=== Exporting total load tables ===")
    for con, df in fu_load_summary.items():
        out_path = OUTPUT_PATH / f"totalLoadperYear_{con}.csv"
        df.to_csv(out_path)
        print(out_path)

    print("\n=== Exporting areal load tables ===")
    for con, df in fu_areal_load_summary.items():
        out_path = OUTPUT_PATH / f"arealLoadperYear_{con}.csv"
        df.to_csv(out_path)
        print(out_path)

    print("\n=== Creating export contribution pie charts ===")
    plot_gbr_export_contribution_pies(
        fu_load_summary=fu_load_summary,
        constituents=CONSTITUENTS,
        output_dir=OUTPUT_PATH,
    )

    print("\n=== Creating tonnage vs areal-load charts ===")
    plot_fu_tonnage_vs_areal_by_region(
        fu_load_summary=fu_load_summary,
        fu_areal_load_summary=fu_areal_load_summary,
        output_dir=OUTPUT_PATH,
    )

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()