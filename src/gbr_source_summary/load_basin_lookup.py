from __future__ import annotations

from pathlib import Path
import pandas as pd


def load_basin_lookup(regions_folder: str | Path) -> pd.DataFrame:
    """
    Load combined GBR subcatchment lookup across all regions.

    Expected columns in each regional LUT:
        - SUBCAT
        - Basin_35
        - Manag_Unit_48

    Parameters
    ----------
    regions_folder : str or Path
        Folder containing regional lookup files such as:
        BM_Subcat_Regions_LUT.xlsx
        CY_Subcat_Regions_LUT.xlsx
        ...

    Returns
    -------
    pd.DataFrame
        Columns:
            Region
            Subcatchment
            Basin_35
            MU_48
    """
    regions_folder = Path(regions_folder)

    lut_files = sorted(regions_folder.glob("*_Subcat_Regions_LUT*"))
    if not lut_files:
        raise FileNotFoundError(
            f"No regional LUT files found in: {regions_folder}"
        )

    dfs = []

    for file in lut_files:
        region = file.name[:2].upper()

        if file.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(file)
        else:
            df = pd.read_csv(file)

        required_cols = {"SUBCAT", "Basin_35", "Manag_Unit_48"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(
                f"{file.name} is missing required columns: {sorted(missing)}"
            )

        out = df.rename(
            columns={
                "SUBCAT": "Subcatchment",
                "Manag_Unit_48": "MU_48",
            }
        ).copy()

        out["Region"] = region

        out["Subcatchment"] = (
            out["Subcatchment"]
            .astype(str)
            .str.strip()
        )

        dfs.append(out[["Region", "Subcatchment", "Basin_35", "MU_48"]])

    basin_lut = pd.concat(dfs, ignore_index=True).drop_duplicates()

    return basin_lut