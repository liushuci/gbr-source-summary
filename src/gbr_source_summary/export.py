"""
Export helpers for gbr_source_summary.

This module provides small utilities for writing summary tables to disk.
Typical outputs include:
- single CSV tables
- multiple region tables
- dictionaries of constituent or scenario tables
- unit-aware report exports
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .units import label_for_units


def ensure_output_dir(output_dir: str | Path) -> Path:
    """
    Create an output directory if it does not already exist.

    Parameters
    ----------
    output_dir : str | Path
        Target folder.

    Returns
    -------
    Path
        Normalised Path object.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    return out


def export_table_csv(
    df: pd.DataFrame,
    output_path: str | Path,
    index: bool = False,
) -> Path:
    """
    Export a single dataframe to CSV.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=index)
    return output_path


def export_region_tables_csv(
    region_tables: dict[str, pd.DataFrame],
    output_dir: str | Path,
    prefix: str = "",
    suffix: str = "",
    index: bool = False,
) -> list[Path]:
    """
    Export one CSV per region.
    """
    out_dir = ensure_output_dir(output_dir)
    outputs: list[Path] = []

    for region, df in region_tables.items():
        filename = f"{prefix}{region}{suffix}.csv"
        output_path = out_dir / filename
        df.to_csv(output_path, index=index)
        outputs.append(output_path)

    return outputs


def export_constituent_tables_csv(
    constituent_tables: dict[str, pd.DataFrame],
    output_dir: str | Path,
    prefix: str = "",
    suffix: str = "",
    index: bool = False,
) -> list[Path]:
    """
    Export one CSV per constituent.
    """
    out_dir = ensure_output_dir(output_dir)
    outputs: list[Path] = []

    for constituent, df in constituent_tables.items():
        filename = f"{prefix}{constituent}{suffix}.csv"
        output_path = out_dir / filename
        df.to_csv(output_path, index=index)
        outputs.append(output_path)

    return outputs


def export_report_tables(
    tables: dict[str, pd.DataFrame],
    output_dir: str | Path,
    units: str,
    export_csv: bool = True,
    index: bool = False,
) -> list[Path]:
    """
    Export reporting tables with unit-aware filenames.

    Examples
    --------
    If units="report", output filenames become:
    - base_fu_report_units.csv
    - predev_fu_report_units.csv
    """
    out_dir = ensure_output_dir(output_dir)
    unit_label = label_for_units(units)
    outputs: list[Path] = []

    for name, df in tables.items():
        filename = f"{name}_{unit_label}"

        if export_csv:
            output_path = out_dir / f"{filename}.csv"
            df.to_csv(output_path, index=index)
        else:
            output_path = out_dir / f"{filename}.xlsx"
            df.to_excel(output_path, index=index)

        outputs.append(output_path)

    return outputs