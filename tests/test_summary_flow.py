import pandas as pd

from gbr_source_summary.summary_flow import (
    build_group_flow_summary,
    build_fu_flow_summary,
    build_basin_flow_summary,
    aggregate_flow_tables,
)


def test_build_group_flow_summary():
    df = pd.DataFrame(
        {
            "Constituent": ["Flow", "Flow", "DIN"],
            "FU": ["Cropping", "Grazing", "Cropping"],
            "LoadToRegExport (kg)": [1000, 2000, 50],
        }
    )

    out = build_group_flow_summary(
        df=df,
        group_column="FU",
        value_column="LoadToRegExport (kg)",
    )

    assert out.loc["Cropping", "LoadToRegExport (kg)"] == 1000
    assert out.loc["Grazing", "LoadToRegExport (kg)"] == 2000
    assert len(out) == 2


def test_build_fu_flow_summary():
    df = pd.DataFrame(
        {
            "Constituent": ["Flow", "Flow"],
            "FU": ["Cropping", "Grazing"],
            "Value": [10, 20],
        }
    )

    out = build_fu_flow_summary(df, value_column="Value")
    assert out.loc["Cropping", "Value"] == 10
    assert out.loc["Grazing", "Value"] == 20


def test_build_basin_flow_summary():
    df = pd.DataFrame(
        {
            "Constituent": ["Flow", "Flow"],
            "Manag_Unit_48": ["B1", "B2"],
            "Value": [100, 200],
        }
    )

    out = build_basin_flow_summary(df, value_column="Value")
    assert out.loc["B1", "Value"] == 100
    assert out.loc["B2", "Value"] == 200


def test_aggregate_flow_tables():
    tables = {
        "CY": pd.DataFrame({"Value": [10]}, index=["Cropping"]),
        "WT": pd.DataFrame({"Value": [20]}, index=["Cropping"]),
    }

    out = aggregate_flow_tables(tables)
    assert out.loc["Cropping", "Value"] == 30