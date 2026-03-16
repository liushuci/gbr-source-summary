from pathlib import Path

import pandas as pd

from gbr_source_summary.export_excel import export_tables_to_excel


def test_export_tables_to_excel(tmp_path):
    tables = {
        "base": pd.DataFrame({"FS": [1], "DIN": [2]}),
        "change": pd.DataFrame({"FS": [3], "DIN": [4]}),
    }

    output = export_tables_to_excel(
        tables=tables,
        output_path=tmp_path / "summary.xlsx",
    )

    assert output.exists()
    assert output.suffix == ".xlsx"