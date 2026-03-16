from pathlib import Path

import pandas as pd

from gbr_source_summary.export import (
    ensure_output_dir,
    export_table_csv,
    export_region_tables_csv,
    export_constituent_tables_csv,
)


def test_ensure_output_dir(tmp_path):
    out = ensure_output_dir(tmp_path / "outputs")
    assert out.exists()
    assert out.is_dir()


def test_export_table_csv(tmp_path):
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    output = export_table_csv(df, tmp_path / "one.csv")
    assert output.exists()


def test_export_region_tables_csv(tmp_path):
    tables = {
        "CY": pd.DataFrame({"FS": [1]}),
        "WT": pd.DataFrame({"FS": [2]}),
    }
    outputs = export_region_tables_csv(tables, tmp_path / "regions", suffix="_summary")
    assert len(outputs) == 2
    assert all(p.exists() for p in outputs)


def test_export_constituent_tables_csv(tmp_path):
    tables = {
        "FS": pd.DataFrame({"Load": [1]}),
        "DIN": pd.DataFrame({"Load": [2]}),
    }
    outputs = export_constituent_tables_csv(tables, tmp_path / "constituents")
    assert len(outputs) == 2
    assert all(p.exists() for p in outputs)