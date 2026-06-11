"""
Modelled-vs-measured annual comparison workflow for gbr_source_summary.

This module converts the original notebook-style GBRCLMP comparison workflow into
reusable functions that can be called from report_card_summary.py.

Main outputs retained:
- collated measured annual data by region/site
- modelled daily and annual data by region/site
- qualityData and allData annual comparisons
- average annual comparison plots by site
- average annual comparison plots by constituent
- annual comparison plots by site/constituent
- monitored/modelled nutrient ratio plots
- Moriasi statistics CSVs by site and whole reporting period

Important naming:
- Fine sediment is handled as FS, not TSS.
- Source model file/folder name for FS is still usually "Sediment - Fine".

Dependencies inside package:
- gbr_source_summary.metrics
- gbr_source_summary.moriasi_ratings
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from gbr_source_summary.metrics import calc_nse, calc_pbias, calc_r2, calc_rsr
from gbr_source_summary.moriasi_ratings import (
    nse_rating,
    pbias_rating,
    r2_rating,
    rsr_rating,
)


KG_TO_T = 0.001
CUMECS_TO_MLD = 86.4

QUALITY_MODES = ["yes", "no"]
QUALITY_RATINGS = ["Excellent", "Good", "Moderate"]

# Constituents read directly from Source time-series folders.
SOURCE_CONSTITUENTS = ["FS", "PN", "DIN", "DON", "PP", "DIP", "DOP", "Flow"]

# Constituents used in comparison outputs. TN and TP are calculated from components.
OUTPUT_CONSTITUENTS = [
    "Flow",
    "FS",
    "TN",
    "PN",
    "DIN",
    "DON",
    "TP",
    "PP",
    "DIP",
    "DOP",
]

# Source model folder/file prefixes. FS maps to the Source output name Sediment - Fine.
SOURCE_PARAMETER_BY_CONSTITUENT = {
    "FS": "Sediment - Fine",
    "PN": "N_Particulate",
    "DIN": "N_DIN",
    "DON": "N_DON",
    "PP": "P_Particulate",
    "DIP": "P_FRP",
    "DOP": "P_DOP",
    "Flow": "Flows",
}

# GBRCLMP files may still use TSS in older exports. The script standardises to FS.
MEASURED_COLUMN_ALIASES = {
    "FS": ["FS", "TSS"],
    "Flow": ["Flow"],
    "TN": ["TN"],
    "PN": ["PN"],
    "DIN": ["DIN"],
    "DON": ["DON"],
    "TP": ["TP"],
    "PP": ["PP"],
    "DIP": ["DIP"],
    "DOP": ["DOP"],
}

SITE_LABELS = {
    "CY": [
        "Pascoe River \n Wattle Station",
        "Laura River \n CoalSeam Creek",
        "E.Normanby River \n Mulligan Highway",
        "W.Normanby River \n Mt Sellheim",
        "Normanby River \n Kalpowar Crossing",
    ],
    "WT": [
        "Barron River \n Myola",
        "S. Johnstone River \n Up. Central Mill",
        "Tully River \n Tully Gorge NP.",
        "Tully River \n Euramo",
        "Herbert River \n John Row Bridge",
        "N. Johnstone River \n Old BruceHwy Bridge",
        "Mulgrave River \n Deeral",
        "Russell River \n East Russell",
        "Johnstone River \n Coquette Point",
    ],
    "BU": [
        "Haughton River \n Powerline",
        "Barratta Creek \n Northcote",
        "Belyando River \n Gregory Dev. Road",
        "Bowen River \n Myuna",
        "Burdekin River \n Home Hill",
        "Burdekin River \n Sellheim",
        "Suttor River \n Bowen Dev. Road",
    ],
    "MW": [
        "O'Connell River \n Stafford's Crossing",
        "Pioneer River \n Dumbleton P. Station",
        "Sandy Creek \n Homebush",
        "Plane Creek \n Sucrogen Weir",
    ],
    "FI": [
        "Fitzroy River \n Fitzroy River Water",
        "Isaac River \n MayDowns Road Bridge",
        "Dawson River \n Neville-Hewitt Weir",
        "MacKenzie River \n Rileys Crossing",
        "Comet River \n Comet Weir",
        "Dawson River \n Taroom",
        "Theresa Creek \n Gregory Highway",
    ],
    "BM": [
        "Burnett River \n B. Anderson Barrage HW.",
        "Burnett River \n Mt Lawless",
        "Mary River \n Fishermans Pocket",
        "Mary River \n HomePark",
        "Tinana Creek \n Barrage HW.",
        "Burnett River \n Eidsvold",
        "Elliott River \n Dr Mays Crossing",
    ],
}


@dataclass
class ModelledMeasuredResult:
    measured_annual_regions: dict[str, dict[str, pd.DataFrame]]
    modelled_daily_regions: dict[str, dict[str, pd.DataFrame]]
    modelled_annual_regions: dict[str, dict[str, pd.DataFrame]]
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]]
    annual_long_quality: dict[str, pd.DataFrame]
    moriasi_quality: pd.DataFrame
    moriasi_all_data: pd.DataFrame


def _ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _quality_folder(q: str) -> str:
    return "qualityData" if q == "yes" else "allData"


def _site_name_col(site_list: pd.DataFrame) -> str | None:
    for col in ["Site Name", "SiteName", "Site_Name", "Name"]:
        if col in site_list.columns:
            return col
    return None


def _require_columns(df: pd.DataFrame, columns: list[str], df_name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"{df_name} is missing required columns: {missing}")


def _site_meta(site_list: pd.DataFrame, region: str) -> pd.DataFrame:
    _require_columns(site_list, ["NRM_short", "Station", "Name_in_Source"], "Site_list")
    out = site_list.loc[site_list["NRM_short"] == region].copy()
    return out


def _standardise_measured_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename older GBRCLMP TSS column to FS if FS is not already present."""
    df = df.copy()
    if "FS" not in df.columns and "TSS" in df.columns:
        df = df.rename(columns={"TSS": "FS"})
    return df


def build_site_list_from_gbrclmp(gbrclmp_file: str | Path) -> pd.DataFrame:
    """
    Build the site metadata table directly from the GBRCLMP master CSV.

    Expected GBRCLMP master columns:
    - Region
    - Site Code
    - Node
    - Display Name

    Optional/fallback columns:
    - Site can be used as a fallback for Site Code
    - Site Name / SiteName / Name can be used as fallback for Display Name

    Returned columns follow the old internal names so the rest of the workflow
    can stay unchanged:
    - NRM_short
    - Station
    - Name_in_Source
    - Site Name
    """
    gbrclmp = pd.read_csv(gbrclmp_file)
    gbrclmp.columns = [str(c).strip() for c in gbrclmp.columns]

    # The new master GBRCLMP file replaces Site_list_wq_q.csv.
    _require_columns(gbrclmp, ["Region", "Node"], "GBRCLMP site metadata")

    station_col = "Site Code" if "Site Code" in gbrclmp.columns else None
    if station_col is None and "Site" in gbrclmp.columns:
        station_col = "Site"

    if station_col is None:
        raise ValueError(
            "GBRCLMP site metadata is missing a site identifier column. "
            "Expected 'Site Code' or 'Site'."
        )

    display_col = None
    for candidate in ["Display Name", "Site Name", "SiteName", "Name"]:
        if candidate in gbrclmp.columns:
            display_col = candidate
            break

    keep_cols = ["Region", station_col, "Node"] + ([display_col] if display_col else [])
    site_list = gbrclmp[keep_cols].drop_duplicates().copy()

    rename_map = {
        "Region": "NRM_short",
        station_col: "Station",
        "Node": "Name_in_Source",
    }
    if display_col:
        rename_map[display_col] = "Site Name"

    site_list = site_list.rename(columns=rename_map)

    if "Site Name" not in site_list.columns:
        site_list["Site Name"] = site_list["Station"]

    site_list["NRM_short"] = site_list["NRM_short"].astype(str).str.strip().str.upper()
    site_list["Station"] = site_list["Station"].astype(str).str.strip()
    site_list["Name_in_Source"] = site_list["Name_in_Source"].astype(str).str.strip()
    site_list["Site Name"] = site_list["Site Name"].astype(str).str.strip()

    site_list["Name_in_Source"] = (
        site_list["Name_in_Source"]
        .astype(str)
        .str.strip()
    )

    site_list["Name_in_Source"] = (
        site_list["Name_in_Source"]
        .replace(
            {
                "": pd.NA,
                "nan": pd.NA,
                "NaN": pd.NA,
                "<NA>": pd.NA,
            }
        )
    )

    site_list = site_list.dropna(
        subset=["NRM_short", "Station", "Name_in_Source"]
    )

    return site_list.drop_duplicates(
        subset=["NRM_short", "Station", "Name_in_Source"]
    ).reset_index(drop=True)


def _measured_col(df: pd.DataFrame, constituent: str) -> str | None:
    for col in MEASURED_COLUMN_ALIASES.get(constituent, [constituent]):
        if col in df.columns:
            return col
    return None


def _source_timeseries_path(
    model_results_prefix: str | Path,
    region: str,
    scenario_folder: str,
    source_node: str,
    constituent: str,
) -> Path:
    model_results_prefix = Path(model_results_prefix)
   


    region = str(region).strip()
    source_node = str(source_node).strip()
    scenario_folder = str(scenario_folder).strip()

    base = (
        model_results_prefix
        / region
        / "Model_Outputs"
        / scenario_folder
        / "TimeSeries"
    )

    if constituent == "Flow":
        return base / "Flows" / f"Flow_{source_node}_cubicmetrespersecond.csv"

    source_parameter = SOURCE_PARAMETER_BY_CONSTITUENT[constituent]
    return base / source_parameter / f"{source_parameter}_{source_node}_kilograms.csv"

def _read_source_timeseries(path: Path) -> pd.Series:
    if not path.exists():
        raise FileNotFoundError(path)

    df = pd.read_csv(path)
    if "Date" not in df.columns:
        raise ValueError(f"Date column not found in {path}")

    value_cols = [c for c in df.columns if c != "Date"]
    if not value_cols:
        raise ValueError(f"No value column found in {path}")

    value_col = value_cols[0]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=["Date"])

    s = df.set_index("Date")[value_col]
    s.name = "value"
    return s


def _water_year_index(index: pd.DatetimeIndex) -> list[str]:
    return [f"{d.year - 1}-{d.year}" for d in index]


def _sort_water_year_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_index(key=lambda idx: [int(str(x).split("-")[0]) for x in idx])


def _unit_label(constituent: str) -> str:
    if constituent == "Flow":
        return "Flow (GL/yr)"
    if constituent == "FS":
        return "FS (kt/yr)"
    return f"{constituent} (t/yr)"


def _plot_ylabel(constituent: str) -> str:
    if constituent == "Flow":
        return "Flow (GL)"
    if constituent == "FS":
        return "FS (kt)"
    if constituent == "PSII TE":
        return "PSII TE (kg)"
    return f"{constituent} (t)"


def collate_measured_annual_regions(
    gbrclmp_file: str | Path,
    site_list: pd.DataFrame,
    regions: list[str],
) -> dict[str, dict[str, pd.DataFrame]]:
    """Collate measured GBRCLMP annual flows/loads by region and site."""
    gbrclmp = pd.read_csv(gbrclmp_file)
    gbrclmp = _standardise_measured_columns(gbrclmp)
    _require_columns(gbrclmp, ["Site Code", "Year", "RepresentivityRating"], "GBRCLMP data")

    measured_annual_regions: dict[str, dict[str, pd.DataFrame]] = {}

    keep_cols = ["RepresentivityRating"] + [c for c in OUTPUT_CONSTITUENTS if c in gbrclmp.columns]

    for region in regions:
        measured_annual_sites: dict[str, pd.DataFrame] = {}
        meta = _site_meta(site_list, region)

        for site in meta["Station"].tolist():
            annual = gbrclmp.loc[gbrclmp["Site Code"] == site].copy()

            if annual.empty:
                measured_annual_sites[site] = pd.DataFrame(columns=keep_cols)
                continue

            annual = annual.set_index("Year")
            annual = annual[[c for c in keep_cols if c in annual.columns]]
            measured_annual_sites[site] = annual

        measured_annual_regions[region] = measured_annual_sites

    return measured_annual_regions

def _find_case_insensitive_file(path: Path) -> Path | None:
    """
    Find a file using case-insensitive filename matching.

    Useful where GBRCLMP Node uses 118103A but Source output file uses 118103a.
    """
    if path.exists():
        return path

    parent = path.parent
    if not parent.exists():
        return None

    target = path.name.lower()

    for candidate in parent.iterdir():
        if candidate.name.lower() == target:
            return candidate

    return None

def build_modelled_daily_and_annual_regions(
    model_results_prefix: str | Path,
    site_list: pd.DataFrame,
    regions: list[str],
    scenario_folder: str = "BASE_Gold_93_23",
    strict: bool = False,
) -> tuple[dict[str, dict[str, pd.DataFrame]], dict[str, dict[str, pd.DataFrame]]]:
    """Read Source daily time series and aggregate to water-year annual totals."""
    modelled_daily_regions: dict[str, dict[str, pd.DataFrame]] = {}
    modelled_annual_regions: dict[str, dict[str, pd.DataFrame]] = {}

    for region in regions:
        modelled_daily_sites: dict[str, pd.DataFrame] = {}
        modelled_annual_sites: dict[str, pd.DataFrame] = {}
        meta = _site_meta(site_list, region)

        for _, row in meta.iterrows():
            site = row["Station"]
            source_node = row["Name_in_Source"]
            daily_parts: dict[str, pd.Series] = {}

            for constituent in SOURCE_CONSTITUENTS:
                path = _source_timeseries_path(
                    model_results_prefix=model_results_prefix,
                    region=region,
                    scenario_folder=scenario_folder,
                    source_node=str(source_node),
                    constituent=constituent,
                )

                try:
                    s = _read_source_timeseries(path)
                except FileNotFoundError:
                    alt_path = _find_case_insensitive_file(path)

                    if alt_path is not None:
                        s = _read_source_timeseries(alt_path)
                    else:
                        msg = f"Missing modelled time series: {path}"
                        if strict:
                            raise FileNotFoundError(msg)
                        warnings.warn(msg)
                        continue

                multiplier = CUMECS_TO_MLD if constituent == "Flow" else KG_TO_T
                daily_parts[constituent] = s * multiplier

            if not daily_parts:
                modelled_daily_sites[site] = pd.DataFrame()
                modelled_annual_sites[site] = pd.DataFrame()
                continue

            daily = pd.DataFrame(daily_parts)
            daily.index = pd.to_datetime(daily.index)

            if {"PN", "DIN", "DON"}.issubset(daily.columns):
                daily["TN"] = daily["PN"] + daily["DIN"] + daily["DON"]

            if {"PP", "DIP", "DOP"}.issubset(daily.columns):
                daily["TP"] = daily["PP"] + daily["DIP"] + daily["DOP"]

            daily = daily[[c for c in OUTPUT_CONSTITUENTS if c in daily.columns]]

            annual = daily.resample("YE-JUN").sum().round(1)
            annual.index = _water_year_index(annual.index)

            modelled_daily_sites[site] = daily
            modelled_annual_sites[site] = annual

        modelled_daily_regions[region] = modelled_daily_sites
        modelled_annual_regions[region] = modelled_annual_sites

    return modelled_daily_regions, modelled_annual_regions


def build_summary_annual_regions_quality(
    measured_annual_regions: dict[str, dict[str, pd.DataFrame]],
    modelled_annual_regions: dict[str, dict[str, pd.DataFrame]],
    site_list: pd.DataFrame,
    regions: list[str],
    min_quality_years: int = 3,
) -> tuple[dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]], dict[str, pd.DataFrame]]:
    """Build nested annual comparison dictionary for qualityData and allData."""
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]] = {}
    annual_long_quality: dict[str, pd.DataFrame] = {}

    for q in QUALITY_MODES:
        summary_annual_regions: dict[str, dict[str, dict[str, pd.DataFrame]]] = {}
        long_rows: list[pd.DataFrame] = []

        for region in regions:
            meta = _site_meta(site_list, region)
            summary_annual_sites: dict[str, dict[str, pd.DataFrame]] = {}

            for site in meta["Station"].tolist():
                measured_site = measured_annual_regions.get(region, {}).get(site, pd.DataFrame())
                modelled_site = modelled_annual_regions.get(region, {}).get(site, pd.DataFrame())
                summary_annual_paras: dict[str, pd.DataFrame] = {}

                for constituent in OUTPUT_CONSTITUENTS:
                    measured_col = _measured_col(measured_site, constituent)

                    if measured_col is None or constituent not in modelled_site.columns:
                        summary_annual_paras[constituent] = pd.DataFrame(columns=["GBRCLMP", "Modelled"])
                        continue

                    measured = measured_site[[measured_col, "RepresentivityRating"]].copy()
                    measured = measured.rename(columns={measured_col: "GBRCLMP"})
                    measured["GBRCLMP"] = pd.to_numeric(measured["GBRCLMP"], errors="coerce")

                    if q == "yes":
                        measured = measured.loc[measured["RepresentivityRating"].isin(QUALITY_RATINGS)]
                        if measured["GBRCLMP"].count() < min_quality_years:
                            summary_annual_paras[constituent] = pd.DataFrame(columns=["GBRCLMP", "Modelled"])
                            continue

                    measured = measured[["GBRCLMP"]].groupby(level=0).mean()
                    modelled = modelled_site[[constituent]].rename(columns={constituent: "Modelled"})
                    modelled["Modelled"] = pd.to_numeric(modelled["Modelled"], errors="coerce")
                    modelled = modelled.groupby(level=0).mean()

                    common_years = measured.index.intersection(modelled.index)
                    compare = pd.concat(
                        [measured.loc[common_years], modelled.loc[common_years]],
                        axis=1,
                    )

                    # Original workflow reported Flow as GL and sediment as kt.
                    # Modelled flow annuals are ML and FS annuals are t before this conversion.
                    # GBRCLMP inputs should follow the same base units as the old workflow.
                    if constituent in ["Flow", "FS"]:
                        compare = compare / 1000.0

                    compare = _sort_water_year_index(compare)
                    summary_annual_paras[constituent] = compare

                    if not compare.empty:
                        long = compare.reset_index().rename(columns={"index": "Year"})
                        long["Region"] = region
                        long["Site"] = site
                        long["Constituent"] = constituent
                        long["QualityOnly"] = q
                        long_rows.append(long)

                summary_annual_sites[site] = summary_annual_paras

            summary_annual_regions[region] = summary_annual_sites

        summary_annual_regions_quality[q] = summary_annual_regions
        annual_long_quality[q] = pd.concat(long_rows, ignore_index=True) if long_rows else pd.DataFrame()

    return summary_annual_regions_quality, annual_long_quality


def _average_annual_by_site(
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]],
    q: str,
    region: str,
    site: str,
) -> pd.DataFrame:
    rows = []

    for constituent in OUTPUT_CONSTITUENTS:
        annuals = summary_annual_regions_quality[q][region][site].get(constituent, pd.DataFrame())
        non_nan = annuals.dropna()
        avg = non_nan.mean(numeric_only=True)
        n = non_nan.count()

        rows.append(
            {
                "Constituent": constituent,
                "GBRCLMP": avg.get("GBRCLMP", np.nan),
                "Modelled": avg.get("Modelled", np.nan),
                "num": n.sum() / 2 if len(n) else 0,
            }
        )

    return pd.DataFrame(rows).set_index("Constituent")


def plot_ratios_by_site(
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]],
    site_list: pd.DataFrame,
    regions: list[str],
    reportcard_outputs_prefix: str | Path,
) -> None:
    reportcard_outputs_prefix = Path(reportcard_outputs_prefix)

    ratio_names = [
        "PN:FS \n(t/kt)",
        "PN:TN \n(t/t)",
        "DIN:TN \n(t/t)",
        "DON:TN \n(t/t)",
        "PP:FS \n(t/kt)",
        "PP:TP \n(t/t)",
        "DIP:TP \n(t/t)",
        "DOP:TP \n(t/t)",
    ]

    for q in QUALITY_MODES:
        for region in regions:
            meta = _site_meta(site_list, region)

            for site in meta["Station"].tolist():
                avg = _average_annual_by_site(summary_annual_regions_quality, q, region, site)

                if avg[["GBRCLMP", "Modelled"]].fillna(0).sum().sum() == 0:
                    continue

                monitored = avg["GBRCLMP"]
                modelled = avg["Modelled"]

                ratios = pd.DataFrame(
                    {
                        "Monitored": [
                            monitored.get("PN") / monitored.get("FS"),
                            monitored.get("PN") / monitored.get("TN"),
                            monitored.get("DIN") / monitored.get("TN"),
                            monitored.get("DON") / monitored.get("TN"),
                            monitored.get("PP") / monitored.get("FS"),
                            monitored.get("PP") / monitored.get("TP"),
                            monitored.get("DIP") / monitored.get("TP"),
                            monitored.get("DOP") / monitored.get("TP"),
                        ],
                        "Modelled": [
                            modelled.get("PN") / modelled.get("FS"),
                            modelled.get("PN") / modelled.get("TN"),
                            modelled.get("DIN") / modelled.get("TN"),
                            modelled.get("DON") / modelled.get("TN"),
                            modelled.get("PP") / modelled.get("FS"),
                            modelled.get("PP") / modelled.get("TP"),
                            modelled.get("DIP") / modelled.get("TP"),
                            modelled.get("DOP") / modelled.get("TP"),
                        ],
                    },
                    index=ratio_names,
                ).replace([np.inf, -np.inf], np.nan)

                if ratios.dropna(how="all").empty:
                    continue

                ax = ratios.plot(
                    kind="bar",
                    fontsize=8,
                    color=["dodgerblue", "tomato"],
                    edgecolor="black",
                )
                ax.set_ylabel("Ratios", size=8)
                ax.legend(["Monitored", "Modelled"], ncol=2, fontsize=8)

                fig = plt.gcf()
                fig.subplots_adjust(bottom=0.1, left=0.0, top=1.0, right=1.3)

                out_dir = _ensure_dir(
                    reportcard_outputs_prefix
                    / region
                    / "modelledVSmeasured"
                    / _quality_folder(q)
                    / "ratios"
                )
                fig.savefig(out_dir / f"{site}.png", dpi=200, bbox_inches="tight")
                plt.close(fig)


def plot_average_annuals_by_site(
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]],
    site_list: pd.DataFrame,
    regions: list[str],
    reportcard_outputs_prefix: str | Path,
) -> None:
    reportcard_outputs_prefix = Path(reportcard_outputs_prefix)
    columns = [_unit_label(c) for c in OUTPUT_CONSTITUENTS]

    for q in QUALITY_MODES:
        for region in regions:
            meta = _site_meta(site_list, region)

            for site in meta["Station"].tolist():
                avg = _average_annual_by_site(summary_annual_regions_quality, q, region, site)

                if avg[["GBRCLMP", "Modelled"]].fillna(0).sum().sum() == 0:
                    continue

                plot_df = avg[["GBRCLMP", "Modelled"]].T
                plot_df.columns = columns

                ax = plot_df.T.plot(
                    kind="bar",
                    fontsize=8,
                    color=["dodgerblue", "tomato"],
                    edgecolor="black",
                )
                ax.set_ylabel("Flow and Loads", size=8)
                ax.legend(["Monitored", "Modelled"], ncol=2, fontsize=8)
                ax.get_yaxis().set_major_formatter(
                    matplotlib.ticker.FuncFormatter(lambda x, _p: format(int(x), ","))
                )

                table_df = avg[["GBRCLMP", "Modelled", "num"]].T
                table_df.columns = columns
                table_df = table_df.fillna(0).astype(float).round(0).astype(int)
                table_df = table_df.map("{:,}".format)

                table = plt.table(
                    cellText=table_df.values,
                    rowLabels=["Monitored", "Modelled", "Years of Data"],
                    colLabels=columns,
                    loc="bottom",
                )
                table.auto_set_font_size(False)
                table.set_fontsize(7)

                fig = plt.gcf()
                fig.subplots_adjust(bottom=0.1, left=0.0, top=1.0, right=1.3)

                out_dir = _ensure_dir(
                    reportcard_outputs_prefix
                    / region
                    / "modelledVSmeasured"
                    / _quality_folder(q)
                    / "averageAnnuals"
                    / "bySites"
                )
                fig.savefig(out_dir / f"averageAnnuals_{site}.png", dpi=200, bbox_inches="tight")
                plt.close(fig)


def plot_average_annuals_by_constituent(
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]],
    site_list: pd.DataFrame,
    regions: list[str],
    reportcard_outputs_prefix: str | Path,
) -> None:
    reportcard_outputs_prefix = Path(reportcard_outputs_prefix)

    for q in QUALITY_MODES:
        for constituent in OUTPUT_CONSTITUENTS:
            for region in regions:
                meta = _site_meta(site_list, region).sort_values("Station")
                sites = meta["Station"].tolist()
                rows = []

                for site in sites:
                    annuals = summary_annual_regions_quality[q][region][site].get(constituent, pd.DataFrame())
                    avg = annuals.dropna().mean(numeric_only=True)
                    if not avg.empty:
                        rows.append(
                            {
                                "Site": site,
                                "Monitored": avg.get("GBRCLMP", np.nan),
                                "Modelled": avg.get("Modelled", np.nan),
                            }
                        )

                if not rows:
                    continue

                plot_df = pd.DataFrame(rows).set_index("Site").dropna(how="all")
                if plot_df.empty:
                    continue

                ax = plot_df.plot(
                    kind="bar",
                    color=["dodgerblue", "tomato"],
                    edgecolor="black",
                )
                ax.set_xlabel("")
                ax.set_ylabel(_plot_ylabel(constituent), size=10)
                ax.legend(
                    ["Monitored", "Modelled"],
                    ncol=2,
                    fontsize=9,
                    loc="lower center",
                    bbox_to_anchor=(0.5, 1),
                )

                labels = SITE_LABELS.get(region)
                if labels and len(labels) >= len(sites):
                    selected_labels = [labels[i] for i, s in enumerate(sites) if s in plot_df.index]
                    if len(selected_labels) == len(plot_df.index):
                        ax.set_xticklabels(selected_labels, rotation=90)

                fig = plt.gcf()
                out_dir = _ensure_dir(
                    reportcard_outputs_prefix
                    / region
                    / "modelledVSmeasured"
                    / _quality_folder(q)
                    / "averageAnnuals"
                    / "byConstituents"
                )
                fig.savefig(out_dir / f"averageAnnuals_{constituent}.png", dpi=200, bbox_inches="tight")
                plt.close(fig)


def plot_annual_comparisons(
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]],
    site_list: pd.DataFrame,
    regions: list[str],
    reportcard_outputs_prefix: str | Path,
) -> None:
    reportcard_outputs_prefix = Path(reportcard_outputs_prefix)

    for q in QUALITY_MODES:
        for region in regions:
            meta = _site_meta(site_list, region)

            for site in meta["Station"].tolist():
                flow_df = summary_annual_regions_quality[q][region][site].get("Flow", pd.DataFrame())
                if flow_df.empty:
                    continue

                for constituent in OUTPUT_CONSTITUENTS:
                    annuals = summary_annual_regions_quality[q][region][site].get(constituent, pd.DataFrame())
                    compare = annuals.dropna()

                    if compare.empty:
                        continue

                    compare = compare.T
                    compare["Avg. Annual"] = compare.T.dropna().mean(numeric_only=True)
                    compare = compare.T

                    ax = compare.dropna().plot(kind="bar")
                    ax.set_ylabel(_plot_ylabel(constituent), size=8)

                    fig = plt.gcf()
                    out_dir = _ensure_dir(
                        reportcard_outputs_prefix
                        / region
                        / "modelledVSmeasured"
                        / _quality_folder(q)
                        / "annuals"
                        / site
                    )
                    fig.savefig(out_dir / f"{constituent}.png", dpi=200, bbox_inches="tight")
                    plt.close(fig)


def build_moriasi_stats(
    summary_annual_regions_quality: dict[str, dict[str, dict[str, dict[str, pd.DataFrame]]]],
    site_list: pd.DataFrame,
    regions: list[str],
    reportcard_outputs_prefix: str | Path,
) -> dict[str, pd.DataFrame]:
    """Calculate and save Moriasi statistics for qualityData and allData."""
    reportcard_outputs_prefix = Path(reportcard_outputs_prefix)
    site_name_col = _site_name_col(site_list)
    outputs: dict[str, pd.DataFrame] = {}

    for q in QUALITY_MODES:
        all_site_dfs = []

        for region in regions:
            meta = _site_meta(site_list, region)
            site_name_map = dict(zip(meta["Station"], meta[site_name_col])) if site_name_col else {}

            for site in meta["Station"].tolist():
                flow_df = summary_annual_regions_quality[q][region][site].get("Flow", pd.DataFrame())
                if flow_df.empty or flow_df["GBRCLMP"].count() < 3:
                    continue

                rows = []
                for constituent in OUTPUT_CONSTITUENTS:
                    annual = summary_annual_regions_quality[q][region][site].get(constituent, pd.DataFrame())
                    clean = annual.copy()

                    # avoid duplicate columns causing clean["Monitored"] to return a DataFrame
                    clean = clean.loc[:, ~clean.columns.duplicated()].copy()

                    clean = clean.rename(columns={"GBRCLMP": "Monitored"})

                    clean["Monitored"] = pd.to_numeric(clean["Monitored"], errors="coerce")
                    clean["Modelled"] = pd.to_numeric(clean["Modelled"], errors="coerce")

                    clean = clean.dropna(subset=["Monitored", "Modelled"])

                    n_years = len(clean)
                    monitored = clean["Monitored"].to_numpy(dtype=float)
                    modelled = clean["Modelled"].to_numpy(dtype=float)

                    rsr = calc_rsr(monitored, modelled)
                    nse = calc_nse(monitored, modelled)
                    r2 = calc_r2(monitored, modelled)
                    pbias = calc_pbias(monitored, modelled)

                    rows.append(
                        {
                            "Region": region,
                            "Site": site,
                            "Site Name": site_name_map.get(site, None),
                            "Constituent": constituent,
                            "Years": n_years,
                            "RSR": rsr,
                            "RSR Rating": rsr_rating(rsr),
                            "NSE": nse,
                            "NSE Rating": nse_rating(nse, constituent),
                            "R2": r2,
                            "R2 Rating": r2_rating(r2, constituent),
                            "PBias": pbias,
                            "PBias Rating": pbias_rating(pbias, constituent),
                        }
                    )

                site_df = pd.DataFrame(rows)
                if site_df.empty:
                    continue

                all_site_dfs.append(site_df)

                suffix = "quality_only" if q == "yes" else "alldata"
                out_dir = _ensure_dir(
                    reportcard_outputs_prefix
                    / region
                    / "modelledVSmeasured"
                    / _quality_folder(q)
                    / "Moriasi"
                )
                site_df.to_csv(out_dir / f"{site}_Moriasi_stats_93_23_{suffix}.csv", index=False)

        final = pd.concat(all_site_dfs, ignore_index=True) if all_site_dfs else pd.DataFrame()

        if q == "yes":
            final.to_csv(
                reportcard_outputs_prefix / "Moriasi_stats_reporting_period_93_23_quality_only.csv",
                index=False,
            )
            outputs["quality"] = final
        else:
            final.to_csv(
                reportcard_outputs_prefix / "Moriasi_stats_reporting_period_93_23.csv",
                index=False,
            )
            outputs["all"] = final

    return outputs


def save_annual_long_outputs(
    annual_long_quality: dict[str, pd.DataFrame],
    reportcard_outputs_prefix: str | Path,
) -> None:
    reportcard_outputs_prefix = _ensure_dir(reportcard_outputs_prefix)

    for q, df in annual_long_quality.items():
        if df.empty:
            continue
        df.to_csv(
            reportcard_outputs_prefix / f"modelled_vs_measured_annual_{_quality_folder(q)}.csv",
            index=False,
        )


def run_modelled_vs_measured(
    gbrclmp_file: str | Path,
    model_results_prefix: str | Path,
    reportcard_outputs_prefix: str | Path,
    regions: list[str],
    scenario_folder: str = "BASE_Gold_93_23",
    make_plots: bool = True,
    strict: bool = False,
) -> ModelledMeasuredResult:
    """
    Main wrapper for report_card_summary.py.

    Parameters
    ----------
    gbrclmp_file
        GBRCLMP annual monitored flow/load CSV.
    The GBRCLMP master CSV must include site metadata columns used to replace
    the old Site_list_wq_q.csv dependency: Region, Site Code, Node and Display Name.
    model_results_prefix
        Folder containing each region/Model_Outputs/<scenario_folder>/TimeSeries.
    reportcard_outputs_prefix
        Output folder. The function will create modelledVSmeasured subfolders.
    regions
        Region codes, e.g. ["CY", "WT", "BU", "MW", "FI", "BM"].
    scenario_folder
        Source model output scenario folder, default BASE_Gold_93_23.
    make_plots
        If False, only CSV outputs and Moriasi tables are created.
    strict
        If True, missing modelled time-series files raise FileNotFoundError.
        If False, missing files are warned and skipped.
    """
    site_list = build_site_list_from_gbrclmp(gbrclmp_file)
    reportcard_outputs_prefix = _ensure_dir(reportcard_outputs_prefix)

    measured_annual_regions = collate_measured_annual_regions(
        gbrclmp_file=gbrclmp_file,
        site_list=site_list,
        regions=regions,
    )

    modelled_daily_regions, modelled_annual_regions = build_modelled_daily_and_annual_regions(
        model_results_prefix=model_results_prefix,
        site_list=site_list,
        regions=regions,
        scenario_folder=scenario_folder,
        strict=strict,
    )

    summary_annual_regions_quality, annual_long_quality = build_summary_annual_regions_quality(
        measured_annual_regions=measured_annual_regions,
        modelled_annual_regions=modelled_annual_regions,
        site_list=site_list,
        regions=regions,
    )

    save_annual_long_outputs(
        annual_long_quality=annual_long_quality,
        reportcard_outputs_prefix=reportcard_outputs_prefix,
    )

    if make_plots:
        plot_ratios_by_site(
            summary_annual_regions_quality=summary_annual_regions_quality,
            site_list=site_list,
            regions=regions,
            reportcard_outputs_prefix=reportcard_outputs_prefix,
        )
        plot_average_annuals_by_site(
            summary_annual_regions_quality=summary_annual_regions_quality,
            site_list=site_list,
            regions=regions,
            reportcard_outputs_prefix=reportcard_outputs_prefix,
        )
        plot_average_annuals_by_constituent(
            summary_annual_regions_quality=summary_annual_regions_quality,
            site_list=site_list,
            regions=regions,
            reportcard_outputs_prefix=reportcard_outputs_prefix,
        )
        plot_annual_comparisons(
            summary_annual_regions_quality=summary_annual_regions_quality,
            site_list=site_list,
            regions=regions,
            reportcard_outputs_prefix=reportcard_outputs_prefix,
        )

    moriasi_outputs = build_moriasi_stats(
        summary_annual_regions_quality=summary_annual_regions_quality,
        site_list=site_list,
        regions=regions,
        reportcard_outputs_prefix=reportcard_outputs_prefix,
    )

    return ModelledMeasuredResult(
        measured_annual_regions=measured_annual_regions,
        modelled_daily_regions=modelled_daily_regions,
        modelled_annual_regions=modelled_annual_regions,
        summary_annual_regions_quality=summary_annual_regions_quality,
        annual_long_quality=annual_long_quality,
        moriasi_quality=moriasi_outputs.get("quality", pd.DataFrame()),
        moriasi_all_data=moriasi_outputs.get("all", pd.DataFrame()),
    )
