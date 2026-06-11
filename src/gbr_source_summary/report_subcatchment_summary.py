"""
Subcatchment-level report-card summary.

Creates FU-aggregated subcatchment summary for all selected constituents
and scenarios.

Output columns
--------------
- Scenario
- Level
- Region
- Basin_35
- MU_48
- Subcatchment
- Constituent
- Units
- Value

Notes
-----
- Fine sediment is FS. Do not use TSS.
- FU is aggregated, so FU column is not exported.
- Process and MetricType columns are not exported.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from .config import GBRConfig
from .export import ensure_output_dir
from .units import label_for_units
from .package_data import package_data_path

SUMMARY_COLUMNS = [
    "Scenario",
    "Level",
    "Region",
    "Basin_35",
    "MU_48",
    "Subcatchment",
    "Constituent",
    "Units",
    "Value",
]


# =============================================================================
# Helpers
# =============================================================================


def _cfg_main_path(cfg: GBRConfig) -> Path:
    return Path(getattr(cfg, "main_path"))


def _normalise_constituents_no_tss(
    constituents: list[str] | None,
) -> list[str] | None:

    if constituents is None:
        return None

    out = [
        str(c).strip().upper()
        for c in constituents
        if str(c).strip()
    ]

    if "TSS" in out:
        raise ValueError(
            "TSS is not supported here. Use FS for fine sediment."
        )

    return out


def _report_unit_for_constituent(
    constituent: str | None,
) -> str:

    key = str(constituent).strip().upper() if constituent else ""

    if key in {"FS", "CS"}:
        return "kt/yr"

    return "t/yr"


def _convert_value_to_report_units(
    value: pd.Series,
    constituent: pd.Series,
    model_years: int,
) -> pd.Series:

    con = constituent.astype(str).str.upper()

    out = pd.to_numeric(
        value,
        errors="coerce",
    ).fillna(0.0)

    sediment_mask = con.isin(["FS", "CS"])
    nutrient_mask = ~sediment_mask

    out.loc[sediment_mask] = (
        out.loc[sediment_mask]
        / 1e6
        / model_years
    )

    out.loc[nutrient_mask] = (
        out.loc[nutrient_mask]
        / 1e3
        / model_years
    )

    return out


def _find_existing_column(
    df: pd.DataFrame,
    candidates: Iterable[str],
) -> str | None:

    lookup = {
        str(c).strip().lower(): c
        for c in df.columns
    }

    for candidate in candidates:
        key = str(candidate).strip().lower()

        if key in lookup:
            return lookup[key]

    return None


# =============================================================================
# LUT
# =============================================================================


def _find_region_lut_path(
    cfg: GBRConfig,
    region: str,
) -> Path:

    region = str(region).strip().upper()

    return Path(
        package_data_path(
            "region_lookup",
            f"{region}_Subcat_Regions_LUT.csv",
        )
    )

def _load_regional_lut(
    cfg: GBRConfig,
    region: str,
) -> pd.DataFrame:
    """
    Load regional Subcat_Regions_LUT and keep Basin_35 + MU48.
    """

    lut_path = _find_region_lut_path(cfg, region)

    #print(f"Using LUT for {region}: {lut_path}")

    lut = pd.read_csv(lut_path)

    subcat_col = _find_existing_column(
        lut,
        [
            "Reg_SC",
            "REG_SC",
            "SUBCAT",
            "Subcat",
            "Subcatchment",
            "Subcatchment_ID",
            "ModelElement",
        ],
    )

    basin35_col = _find_existing_column(
        lut,
        [
            "Basin_35",
            "BASIN_35",
            "Basin35",
            "Basin",
        ],
    )

    mu48_col = _find_existing_column(
        lut,
        [
            "Manag_Unit_48",
            "MANAG_UNIT_48",
            "MU_48",
            "MU48",
            "Management_Unit_48",
        ],
    )

    missing = []

    if subcat_col is None:
        missing.append("Reg_SC/Subcatchment")

    if basin35_col is None:
        missing.append("Basin_35")

    if mu48_col is None:
        missing.append("Manag_Unit_48/MU_48")

    if missing:
        raise ValueError(
            f"LUT for {region} is missing required columns: "
            f"{missing}. "
            f"File: {lut_path}. "
            f"Available columns: {list(lut.columns)}"
        )

    lut = lut[
        [
            subcat_col,
            basin35_col,
            mu48_col,
        ]
    ].copy()

    lut = lut.rename(
        columns={
            subcat_col: "Subcatchment",
            basin35_col: "Basin_35",
            mu48_col: "MU_48",
        }
    )

    lut["Subcatchment"] = (
        lut["Subcatchment"]
        .astype(str)
        .str.strip()
    )

    lut = lut.drop_duplicates(
        subset=["Subcatchment"],
        keep="first",
    )

    return lut


# =============================================================================
# RegContributor
# =============================================================================


def _load_regcontributor(
    cfg: GBRConfig,
    region: str,
    scenario: str,
) -> pd.DataFrame:
    """
    Load RegContributorDataGrid.csv for one region/scenario.

    Uses cfg.get_model_output_dir(), which auto-detects folders such as:
    PREDEV_RC2022
    PREDEV_Gold_93_23
    """

    file_path = (
        cfg.get_model_output_dir(region, scenario)
        / "RegContributorDataGrid.csv"
    )

    if not file_path.exists():
        raise FileNotFoundError(
            f"Could not find RegContributorDataGrid.csv for "
            f"{region} {scenario}: {file_path}"
        )

    return pd.read_csv(file_path, low_memory=False)


# =============================================================================
# Constituents
# =============================================================================


def _standardise_constituent(
    value: object,
) -> str:

    text = str(value).strip()

    mapping = {
        "SEDIMENT - FINE": "FS",
        "SEDIMENT_FINE": "FS",
        "FINE SEDIMENT": "FS",
        "FS": "FS",
        "TSS": "FS",

        "SEDIMENT - COARSE": "CS",
        "SEDIMENT_COARSE": "CS",
        "COARSE SEDIMENT": "CS",
        "CS": "CS",

        "N_PARTICULATE": "PN",
        "PN": "PN",

        "P_PARTICULATE": "PP",
        "PP": "PP",

        "N_DIN": "DIN",
        "DIN": "DIN",

        "N_DON": "DON",
        "DON": "DON",

        "P_FRP": "DIP",
        "DIP": "DIP",

        "P_DOP": "DOP",
        "DOP": "DOP",
    }

    return mapping.get(
        text.upper(),
        text.upper(),
    )


# =============================================================================
# Main build
# =============================================================================


def build_subcatchment_summary(
    cfg: GBRConfig,
    output_dir: str | Path | None = None,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    model: str | None = None,
    scenario: str | None = None,
    scenarios: list[str] | None = None,
    bundle_dirs: dict[str, Path] | None = None,
) -> pd.DataFrame:

    constituents = _normalise_constituents_no_tss(
        constituents
    )

    scenario_list = scenarios or [
        scenario
        or model
        or process_model
        or "BASE"
    ]

    scenario_list = [
        str(s).strip().upper()
        for s in scenario_list
        if str(s).strip()
    ]

    region_list = (
        regions
        or getattr(cfg, "regions", None)
    )

    if not region_list:
        raise ValueError(
            "No regions supplied."
        )

    model_years = int(
        getattr(cfg, "model_years", 30)
    )

    frames: list[pd.DataFrame] = []

    for scenario_name in scenario_list:

        for region in region_list:

            region = str(region).strip().upper()

            # print(
            #     f"Building subcatchment summary: "
            #     f"{region} {scenario_name}"
            # )

            df = _load_regcontributor(
                cfg=cfg,
                region=region,
                scenario=scenario_name,
            )

            lut = _load_regional_lut(
                cfg=cfg,
                region=region,
            )

            subcat_col = _find_existing_column(
                df,
                [
                    "Reg_SC",
                    "ModelElement",
                    "Subcatchment",
                    "Subcat",
                    "SUBCAT",
                ],
            )

            con_col = _find_existing_column(
                df,
                [
                    "Constituent",
                    "ConstituentName",
                    "Constituent_Name",
                ],
            )

            if subcat_col is None:
                raise ValueError(
                    f"Cannot find subcatchment column "
                    f"in {region} RegContributorDataGrid."
                )

            if con_col is None:
                raise ValueError(
                    f"Cannot find constituent column "
                    f"in {region} RegContributorDataGrid."
                )

            if value_column not in df.columns:
                raise ValueError(
                    f"Value column '{value_column}' "
                    f"not found for {region}."
                )

            temp = df[
                [
                    subcat_col,
                    con_col,
                    value_column,
                ]
            ].copy()

            temp = temp.rename(
                columns={
                    subcat_col: "Subcatchment",
                    con_col: "Constituent",
                    value_column: "Value",
                }
            )

            temp["Subcatchment"] = (
                temp["Subcatchment"]
                .astype(str)
                .str.strip()
            )

            temp["Constituent"] = temp[
                "Constituent"
            ].map(_standardise_constituent)

            if constituents:
                temp = temp[
                    temp["Constituent"].isin(
                        constituents
                    )
                ].copy()

            temp["Value"] = pd.to_numeric(
                temp["Value"],
                errors="coerce",
            ).fillna(0.0)

            grouped = (
                temp.groupby(
                    [
                        "Subcatchment",
                        "Constituent",
                    ],
                    dropna=False,
                )["Value"]
                .sum()
                .reset_index()
            )

            grouped = grouped.merge(
                lut,
                on="Subcatchment",
                how="left",
            )

            grouped["Scenario"] = scenario_name
            grouped["Level"] = "Subcatchment"
            grouped["Region"] = region

            if units == "report":

                grouped["Value"] = (
                    _convert_value_to_report_units(
                        grouped["Value"],
                        grouped["Constituent"],
                        model_years=model_years,
                    )
                )

                grouped["Units"] = grouped[
                    "Constituent"
                ].map(
                    _report_unit_for_constituent
                )

            else:
                grouped["Units"] = units

            grouped = grouped[
                SUMMARY_COLUMNS
            ]

            frames.append(grouped)

    if not frames:
        return pd.DataFrame(
            columns=SUMMARY_COLUMNS
        )

    out = pd.concat(
        frames,
        ignore_index=True,
    )

    out = out.sort_values(
        [
            "Scenario",
            "Region",
            "Basin_35",
            "MU_48",
            "Subcatchment",
            "Constituent",
        ],
        na_position="last",
    ).reset_index(drop=True)

    return out


# =============================================================================
# Export
# =============================================================================


def export_subcatchment_summary(
    df: pd.DataFrame,
    output_dir: str | Path,
    units: str = "report",
) -> dict[str, Path]:

    out_dir = ensure_output_dir(
        output_dir
    )

    unit_label = label_for_units(
        units
    )

    output_csv = (
        out_dir
        / (
            f"report_card_summary_subcatchment_"
            f"{unit_label}.csv"
        )
    )

    df.to_csv(
        output_csv,
        index=False,
    )

    return {
        "subcatchment_summary_csv": output_csv,
    }


# =============================================================================
# Runner
# =============================================================================


def run_subcatchment_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    model: str | None = None,
    scenario: str | None = None,
    scenarios: list[str] | None = None,
    bundle_dirs: dict[str, Path] | None = None,
    export_excel_workbook: bool = False,
) -> dict[str, object]:

    summary = build_subcatchment_summary(
        cfg=cfg,
        output_dir=output_dir,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        process_model=process_model,
        model=model,
        scenario=scenario,
        scenarios=scenarios,
        bundle_dirs=bundle_dirs,
    )

    files = export_subcatchment_summary(
        df=summary,
        output_dir=output_dir,
        units=units,
    )

    return {
        "subcatchment_summary": summary,
        "files": files,
    }


# =============================================================================
# Backward compatibility
# =============================================================================


def run_subcatchment_report_card_summary(
    cfg: GBRConfig,
    output_dir: str | Path,
    regions: list[str] | None = None,
    constituents: list[str] | None = None,
    value_column: str = "LoadToRegExport (kg)",
    units: str = "report",
    process_model: str = "BASE",
    model: str | None = None,
    scenario: str | None = None,
    scenarios: list[str] | None = None,
    bundle_dirs: dict[str, Path] | None = None,
    export_excel_workbook: bool = False,
) -> dict[str, object]:

    return run_subcatchment_summary(
        cfg=cfg,
        output_dir=output_dir,
        regions=regions,
        constituents=constituents,
        value_column=value_column,
        units=units,
        process_model=process_model,
        model=model,
        scenario=scenario,
        scenarios=scenarios,
        bundle_dirs=bundle_dirs,
        export_excel_workbook=export_excel_workbook,
    )