import pandas as pd

from gbr_source_summary.summary_fu import (
    build_basin_fu_summary,
    aggregate_region_fu_summary,
    aggregate_gbr_fu_summary,
)


def test_build_basin_fu_summary():
    df = pd.DataFrame(
        {
            "Manag_Unit_48": ["B1", "B1", "B1", "B1"],
            "Constituent": ["FS", "FS", "DIN", "DIN"],
            "FU": ["Dryland Cropping", "Urban", "Irrigated Cropping", "Other"],
            "LoadToRegExport (kg)": [100, 50, 200, 20],
        }
    )

    fus = ["Cropping", "Urban + Other", "Bananas"]
    constituents = ["FS", "DIN"]

    out = build_basin_fu_summary(
        df=df,
        constituents=constituents,
        fus_of_interest=fus,
        value_column="LoadToRegExport (kg)",
    )

    assert "B1" in out
    basin_df = out["B1"]

    assert basin_df.loc["Cropping", "FS"] == 100
    assert basin_df.loc["Cropping", "DIN"] == 200
    assert basin_df.loc["Urban + Other", "FS"] == 50
    assert basin_df.loc["Urban + Other", "DIN"] == 20
    assert pd.isna(basin_df.loc["Bananas", "FS"])


def test_aggregate_region_fu_summary():
    basin_summary = {
        "B1": pd.DataFrame({"FS": [10, 20], "DIN": [1, 2]}, index=["Cropping", "Urban + Other"]),
        "B2": pd.DataFrame({"FS": [30, 40], "DIN": [3, 4]}, index=["Cropping", "Urban + Other"]),
    }

    out = aggregate_region_fu_summary(basin_summary)

    assert out.loc["Cropping", "FS"] == 40
    assert out.loc["Urban + Other", "DIN"] == 6


def test_aggregate_gbr_fu_summary():
    region_summaries = {
        "CY": pd.DataFrame({"FS": [10], "DIN": [1]}, index=["Cropping"]),
        "WT": pd.DataFrame({"FS": [30], "DIN": [3]}, index=["Cropping"]),
    }

    out = aggregate_gbr_fu_summary(region_summaries)

    assert out.loc["Cropping", "FS"] == 40
    assert out.loc["Cropping", "DIN"] == 4