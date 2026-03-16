from __future__ import annotations

from pathlib import Path

import pandas as pd


def export_tables_to_excel(
    tables: dict[str, pd.DataFrame],
    output_path: str | Path,
    index: bool = False,
) -> Path:
    try:
        import openpyxl  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "openpyxl is required for Excel export. "
            "Install it with: pip install openpyxl"
        ) from e

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in tables.items():
            safe_sheet_name = str(sheet_name)[:31]
            df.to_excel(writer, sheet_name=safe_sheet_name, index=index)

    return output_path