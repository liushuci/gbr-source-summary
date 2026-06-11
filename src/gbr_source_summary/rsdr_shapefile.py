from __future__ import annotations

from pathlib import Path
from typing import Iterable
from .package_data import package_data_path

import pandas as pd

try:
    import geopandas as gpd
    HAS_GEOPANDAS = True
except ImportError:
    gpd = None
    HAS_GEOPANDAS = False


CONSTITUENT_MAP = {
    "FS": "Sediment - Fine",
    "PP": "P_Particulate",
    "DIP": "P_FRP",
    "DOP": "P_DOP",
    "PN": "N_Particulate",
    "DIN": "N_DIN",
    "DON": "N_DON",
    "Sediment - Fine": "Sediment - Fine",
    "P_Particulate": "P_Particulate",
    "P_FRP": "P_FRP",
    "P_DOP": "P_DOP",
    "N_Particulate": "N_Particulate",
    "N_DIN": "N_DIN",
    "N_DON": "N_DON",
}

CONSTITUENT_ABBREVIATIONS = {
    "Sediment - Fine": "FS",
    "P_Particulate": "PP",
    "P_FRP": "DIP",
    "P_DOP": "DOP",
    "N_Particulate": "PN",
    "N_DIN": "DIN",
    "N_DON": "DON",
}

RSDR_OVERRIDES = {
    "BU-SC #91708": 1.0,
    "FI-SC #91877": 1.0,
    "FI-SC #91876": 1.0,
    "CY-SC #31": 1.0,
    "CY-SC #33": 1.0,
}


def _normalise_constituents(constituents: Iterable[str] | None) -> list[str]:
    if not constituents:
        return [
            "Sediment - Fine",
            "N_Particulate",
            "P_Particulate",
            "N_DIN",
            "N_DON",
            "P_FRP",
            "P_DOP",
        ]

    out: list[str] = []

    for c in constituents:
        key = str(c).strip()
        if not key:
            continue

        key_upper = key.upper()

        if key_upper == "TSS":
            raise ValueError("TSS is not supported. Use FS for fine sediment.")

        source_name = CONSTITUENT_MAP.get(key_upper, CONSTITUENT_MAP.get(key))

        if source_name and source_name not in out:
            out.append(source_name)

    return out


def _constituent_abbrev(source_constituent: str) -> str:
    return CONSTITUENT_ABBREVIATIONS.get(source_constituent, "XX")


def _safe_region_name(region: str) -> str:
    return str(region).strip().upper()


def _ensure_reg_sc(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure a dataframe has the unique GBR join key Reg_SC.

    Do not join RSDR by Catchmt/SUBCAT only, because SC numbers are repeated
    across regions.
    """
    df = df.copy()

    if "Reg_SC" in df.columns:
        df["Reg_SC"] = df["Reg_SC"].astype(str)
        return df

    if "Region" not in df.columns:
        raise ValueError("Dataframe must contain either Reg_SC or Region.")

    if "ModelElement" in df.columns:
        model_col = "ModelElement"
    elif "Catchmt" in df.columns:
        model_col = "Catchmt"
    elif "SUBCAT" in df.columns:
        model_col = "SUBCAT"
    elif "CATCHMENT" in df.columns:
        model_col = "CATCHMENT"
    else:
        raise ValueError(
            "Dataframe must contain ModelElement, Catchmt, SUBCAT, or CATCHMENT "
            "to create Reg_SC."
        )

    df["Reg_SC"] = (
        df["Region"].astype(str).str.upper()
        + "-"
        + df[model_col].astype(str)
    )

    return df

def _find_subcat_spatial_files(
    regions: list[str],
) -> list[Path]:

    files = []

    for region in regions:

        shp = Path(
            package_data_path(
                "spatial",
                "regions_shp",
                region,
                f"{region}_GBR_Regions_Subcats_P4_v4.shp",
            )
        )

        if not shp.exists():
            raise FileNotFoundError(
                f"Regional shapefile not found: {shp}"
            )

        files.append(shp)

    return files



def _find_reg_contributor_for_region(
    *,
    main_path: Path,
    region: str,
    process_model: str,
    rc: str,
) -> Path | None:
    region_root = main_path / region

    candidate_model_names = [
        f"{process_model}_{rc}",
        f"{process_model.upper()}_{rc}",
        f"{process_model.lower()}_{rc}",
        process_model,
        process_model.upper(),
        process_model.lower(),
    ]

    possible_paths: list[Path] = []
    for model_name in candidate_model_names:
        possible_paths.extend(
            [
                region_root / "Model_Outputs" / model_name / "RegContributorDataGrid.csv",
                region_root / model_name / "RegContributorDataGrid.csv",
            ]
        )

    for path in possible_paths:
        if path.exists():
            return path

    if not region_root.exists():
        return None

    matches = sorted(region_root.rglob("RegContributorDataGrid.csv"))
    process_upper = process_model.upper()
    rc_upper = str(rc).upper()

    preferred = [
        p for p in matches
        if process_upper in str(p).upper() and rc_upper in str(p).upper()
    ]
    if preferred:
        return preferred[0]

    preferred = [p for p in matches if process_upper in str(p).upper()]
    if preferred:
        return preferred[0]

    return matches[0] if matches else None


def _read_reg_contributor_tables(
    *,
    cfg,
    process_model: str,
) -> pd.DataFrame:

    main_path = Path(cfg.main_path)
    regions = getattr(cfg, "regions", []) or []

    model_results_root = (
        main_path / "Gold_ResultsSets_PointOfTruth"
    )

    process_model = process_model.upper()

    if process_model == "BASE":
        scenario_name = f"BASE_{cfg.rc}"
    elif process_model == "PREDEV":
        scenario_name = f"PREDEV_{cfg.rc}"
    elif process_model == "CHANGE":
        scenario_name = f"CHANGE_{cfg.rc}"
    else:
        scenario_name = process_model

    frames = []
    csv_paths = []

    for region in regions:

        csv_path = (
            model_results_root
            / region
            / "Model_Outputs"
            / scenario_name
            / "RegContributorDataGrid.csv"
        )

        if not csv_path.exists():
            print(f"WARNING: Missing {csv_path}")
            continue

        print(f"Reading {region}: {csv_path}")

        df = pd.read_csv(csv_path)

        df["Region"] = region

        df["Reg_SC"] = (
            df["Region"].astype(str)
            + "-"
            + df["ModelElement"].astype(str)
        )

        frames.append(df)
        csv_paths.append(csv_path)

    if not frames:
        raise FileNotFoundError(
            "No RegContributorDataGrid.csv files found."
        )

    return (
        pd.concat(frames, ignore_index=True),
        csv_paths,
    )


def _prepare_rsdr_table(*, reg_cont: pd.DataFrame, source_constituent: str) -> pd.DataFrame:
    relevant = reg_cont.loc[reg_cont["Constituent"] == source_constituent].copy()

    if relevant.empty:
        print(f"WARNING: No RSDR rows found for {source_constituent}")
        return pd.DataFrame()

    relevant = _ensure_reg_sc(relevant)

    agg_cols = {"RSDR": "first"}
    for col in ["Basin_35", "Manag_Unit_48", "MU_48"]:
        if col in relevant.columns:
            agg_cols[col] = "first"

    rsdr = (
        relevant
        .groupby("Reg_SC", as_index=False, dropna=False)
        .agg(agg_cols)
        .copy()
    )

    rsdr["Reg_SC"] = rsdr["Reg_SC"].astype(str)
    rsdr["RSDR"] = pd.to_numeric(rsdr["RSDR"], errors="coerce")

    for reg_sc, value in RSDR_OVERRIDES.items():
        rsdr.loc[rsdr["Reg_SC"] == reg_sc, "RSDR"] = value

    gt1_mask = rsdr["RSDR"] > 1
    if gt1_mask.any():
        print(
            f"{source_constituent}: {int(gt1_mask.sum())} RSDR values > 1; capped to 1."
        )
        print(f"  Max before capping: {rsdr['RSDR'].max()}")

    rsdr.loc[gt1_mask, "RSDR"] = 1.0
    rsdr["RSDR"] = rsdr["RSDR"].round(2)

    return rsdr


def _build_rsdr_long_table(
    *,
    reg_cont: pd.DataFrame,
    subcat_attrs: pd.DataFrame,
    constituents: list[str],
) -> pd.DataFrame:
    """
    Build long RSDR table with one row per subcatchment per constituent.
    """
    frames: list[pd.DataFrame] = []
    subcat_attrs = _ensure_reg_sc(subcat_attrs)

    for source_constituent in constituents:
        abbrev = _constituent_abbrev(source_constituent)

        rsdr = _prepare_rsdr_table(
            reg_cont=reg_cont,
            source_constituent=source_constituent,
        )

        if rsdr.empty:
            continue

        rsdr = rsdr[["Reg_SC", "RSDR"]].copy()
        rsdr["Constituent"] = abbrev
        rsdr["SourceConstituent"] = source_constituent

        joined = subcat_attrs.merge(
            rsdr,
            on="Reg_SC",
            how="left",
        )

        frames.append(joined)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def _build_rsdr_wide_table(
    *,
    reg_cont: pd.DataFrame,
    subcat_attrs: pd.DataFrame,
    constituents: list[str],
) -> pd.DataFrame:
    """
    Build wide RSDR table with one row per subcatchment.
    """
    out = _ensure_reg_sc(subcat_attrs)

    for source_constituent in constituents:
        abbrev = _constituent_abbrev(source_constituent)
        col = f"{abbrev}_RSDR"

        rsdr = _prepare_rsdr_table(
            reg_cont=reg_cont,
            source_constituent=source_constituent,
        )

        if rsdr.empty:
            out[col] = pd.NA
            continue

        rsdr = rsdr[["Reg_SC", "RSDR"]].rename(columns={"RSDR": col})

        out = out.merge(
            rsdr,
            on="Reg_SC",
            how="left",
        )

    return out


def export_rsdr_shapefiles(
    *,
    cfg,
    output_dir: str | Path,
    process_model: str = "BASE",
    constituents: Iterable[str] | None = None,
) -> dict[str, object]:
    """
    Export RSDR outputs as CSV and shapefile.

    Folder structure:
        12_rsdr/
            csv/GBR/GBR_BASE_all_RSDR.csv
            csv/GBR/GBR_BASE_wide_RSDR.csv
            csv/<REGION>/<REGION>_BASE_<CONST>_RSDR.csv
            csv/<REGION>/<REGION>_BASE_all_RSDR.csv
            csv/<REGION>/<REGION>_BASE_wide_RSDR.csv
            shp/GBR/GBR_BASE_all_RSDR.shp
            shp/<REGION>/<REGION>_BASE_<CONST>_RSDR.shp
            shp/<REGION>/<REGION>_BASE_all_RSDR.shp
    """
    output_dir = Path(output_dir)
    csv_root = output_dir / "csv"
    shp_root = output_dir / "shp"

    csv_root.mkdir(parents=True, exist_ok=True)
    shp_root.mkdir(parents=True, exist_ok=True)

    selected_regions = [_safe_region_name(r) for r in getattr(cfg, "regions", []) or []]
    selected_constituents = _normalise_constituents(constituents)
    process_model = str(process_model).upper()

    reg_cont, reg_csv_paths = _read_reg_contributor_tables(
        cfg=cfg,
        process_model=process_model,
    )

    required_cols = {"ModelElement", "Constituent", "AreaM2", "RSDR", "Region", "Reg_SC"}
    missing = required_cols - set(reg_cont.columns)
    if missing:
        raise ValueError(
            "RegContributorDataGrid data missing required columns: "
            f"{sorted(missing)}"
        )

    reg_cont = reg_cont.loc[
        pd.to_numeric(reg_cont["AreaM2"], errors="coerce").fillna(0) != 0
    ].copy()

    shp_paths = _find_subcat_spatial_files(selected_regions)

    if not HAS_GEOPANDAS:
        print(
            "GeoPandas is not installed. CSV outputs will be created, "
            "but shapefile outputs will be skipped."
        )
        subcats = None
        csv_attr_path = shp_path.with_suffix(".csv")

        if not csv_attr_path.exists():
            raise ImportError(
                "GeoPandas is required to read the subcatchment shapefile. "
                "Install geopandas or provide a CSV copy of the subcatchment "
                "attribute table beside the shapefile."
            )

        subcat_attrs = pd.read_csv(csv_attr_path)

        if selected_regions and "Region" in subcat_attrs.columns:
            subcat_attrs = subcat_attrs.loc[
                subcat_attrs["Region"].astype(str).str.upper().isin(selected_regions)
            ].copy()

        subcat_attrs = _ensure_reg_sc(subcat_attrs)

    else:
        frames = []

        for shp_path in shp_paths:

            print(f"Reading subcatchment shapefile: {shp_path}")

            gdf = gpd.read_file(shp_path)

            frames.append(gdf)

        subcats = pd.concat(
            frames,
            ignore_index=True,
        )

        subcats = gpd.GeoDataFrame(
            subcats,
            geometry="geometry",
            crs=frames[0].crs,
        )

        if "SUBCAT" in subcats.columns and "Catchmt" not in subcats.columns:
            subcats["Catchmt"] = subcats["SUBCAT"]

        if "Catchmt" not in subcats.columns:
            raise ValueError("Subcatchment shapefile must contain Catchmt or SUBCAT field.")

        if "Region" not in subcats.columns:
            raise ValueError("Subcatchment shapefile must contain Region field.")

        subcats = _ensure_reg_sc(subcats)

        if selected_regions:
            subcats = subcats.loc[
                subcats["Region"].astype(str).str.upper().isin(selected_regions)
            ].copy()

        attr_cols = [
            c for c in [
                "FID", "SUBCAT", "LINK", "Region", "Reg_SC", "Basin_35",
                "MU_48", "WQI_Cal", "Catchmt", "AREA_M2",
            ] if c in subcats.columns
        ]

        subcat_attrs = pd.DataFrame(subcats[attr_cols]).copy()
        subcat_attrs = _ensure_reg_sc(subcat_attrs)

    files: dict[str, Path] = {}

    if subcat_attrs.empty:
        print("WARNING: No subcatchments found after region filtering.")
        return {
            "files": files,
            "message": "No subcatchments found after region filtering.",
        }

    all_long = _build_rsdr_long_table(
        reg_cont=reg_cont,
        subcat_attrs=subcat_attrs,
        constituents=selected_constituents,
    )

    all_wide = _build_rsdr_wide_table(
        reg_cont=reg_cont,
        subcat_attrs=subcat_attrs,
        constituents=selected_constituents,
    )

    gbr_csv_dir = csv_root / "GBR"
    gbr_csv_dir.mkdir(parents=True, exist_ok=True)

    gbr_all_csv = gbr_csv_dir / f"GBR_{process_model}_all_RSDR.csv"
    all_long.to_csv(gbr_all_csv, index=False)
    files["rsdr_gbr_all_csv"] = gbr_all_csv

    gbr_wide_csv = gbr_csv_dir / f"GBR_{process_model}_wide_RSDR.csv"
    all_wide.to_csv(gbr_wide_csv, index=False)
    files["rsdr_gbr_wide_csv"] = gbr_wide_csv

    if HAS_GEOPANDAS and subcats is not None:
        gbr_shp_dir = shp_root / "GBR"
        gbr_shp_dir.mkdir(parents=True, exist_ok=True)

        rsdr_cols = [c for c in all_wide.columns if c.endswith("_RSDR")]
        gbr_wide_for_join = all_wide[["Reg_SC"] + rsdr_cols].copy()

        gbr_gdf = subcats.merge(
            gbr_wide_for_join,
            on="Reg_SC",
            how="left",
        )

        gbr_wide_shp = gbr_shp_dir / f"GBR_{process_model}_all_RSDR.shp"
        gbr_gdf.to_file(gbr_wide_shp)
        files["rsdr_gbr_all_shp"] = gbr_wide_shp

    region_values = (
        sorted(all_wide["Region"].dropna().astype(str).str.upper().unique())
        if "Region" in all_wide.columns
        else selected_regions
    )

    for region in region_values:
        region = _safe_region_name(region)

        region_csv_dir = csv_root / region
        region_shp_dir = shp_root / region

        region_csv_dir.mkdir(parents=True, exist_ok=True)
        region_shp_dir.mkdir(parents=True, exist_ok=True)

        region_long = all_long.loc[
            all_long["Region"].astype(str).str.upper() == region
        ].copy()

        region_wide = all_wide.loc[
            all_wide["Region"].astype(str).str.upper() == region
        ].copy()

        if region_long.empty:
            continue

        region_all_csv = region_csv_dir / f"{region}_{process_model}_all_RSDR.csv"
        region_long.to_csv(region_all_csv, index=False)
        files[f"rsdr_{region}_all_csv"] = region_all_csv

        region_wide_csv = region_csv_dir / f"{region}_{process_model}_wide_RSDR.csv"
        region_wide.to_csv(region_wide_csv, index=False)
        files[f"rsdr_{region}_wide_csv"] = region_wide_csv

        for source_constituent in selected_constituents:
            abbrev = _constituent_abbrev(source_constituent)
            const_col = f"{abbrev}_RSDR"

            const_csv = region_csv_dir / f"{region}_{process_model}_{abbrev}_RSDR.csv"
            const_df = region_long.loc[
                region_long["SourceConstituent"] == source_constituent
            ].copy()
            const_df.to_csv(const_csv, index=False)
            files[f"rsdr_{region}_{abbrev}_csv"] = const_csv

            if HAS_GEOPANDAS and subcats is not None:
                region_subcats = subcats.loc[
                    subcats["Region"].astype(str).str.upper() == region
                ].copy()

                if const_col in region_wide.columns:
                    const_rsdr = region_wide[["Reg_SC", const_col]].copy()
                else:
                    const_rsdr = region_wide[["Reg_SC"]].copy()
                    const_rsdr[const_col] = pd.NA

                region_const_gdf = region_subcats.merge(
                    const_rsdr,
                    on="Reg_SC",
                    how="left",
                )

                const_shp = region_shp_dir / f"{region}_{process_model}_{abbrev}_RSDR.shp"
                region_const_gdf.to_file(const_shp)
                files[f"rsdr_{region}_{abbrev}_shp"] = const_shp

        if HAS_GEOPANDAS and subcats is not None:
            region_subcats = subcats.loc[
                subcats["Region"].astype(str).str.upper() == region
            ].copy()

            rsdr_cols = [c for c in region_wide.columns if c.endswith("_RSDR")]
            region_wide_for_join = region_wide[["Reg_SC"] + rsdr_cols].copy()

            region_all_gdf = region_subcats.merge(
                region_wide_for_join,
                on="Reg_SC",
                how="left",
            )

            region_all_shp = region_shp_dir / f"{region}_{process_model}_all_RSDR.shp"
            region_all_gdf.to_file(region_all_shp)
            files[f"rsdr_{region}_all_shp"] = region_all_shp

    print("RSDR export complete.")
    print(f"CSV root: {csv_root}")

    if HAS_GEOPANDAS:
        print(f"SHP root: {shp_root}")
    else:
        print("SHP export skipped because GeoPandas is not installed.")

    return {
        "files": files,
        "csv_root": csv_root,
        "shp_root": shp_root if HAS_GEOPANDAS else None,
        "reg_contributor_csvs": reg_csv_paths,
        "subcat_shapefiles": shp_paths,
        "message": "RSDR CSV and shapefile export completed.",
    }
