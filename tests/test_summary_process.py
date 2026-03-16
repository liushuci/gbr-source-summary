import pandas as pd

from gbr_source_summary.summary_process import (
    build_basin_process_summary,
    aggregate_region_process_summary,
    aggregate_gbr_process_summary,
)


def test_build_basin_process_summary():
    df = pd.DataFrame(
        {
            "Manag_Unit_48": ["B1", "B1", "B1", "B1", "B1", "B1"],
            "Constituent": ["FS", "FS", "FS", "DIN", "DIN", "DIN"],
            "Process": [
                "Hillslope surface soil",
                "Streambank",
                "Gully",
                "Diffuse Dissolved",
                "Seepage",
                "Point Source",
            ],
            "LoadToRegExport (kg)": [100, 50, 25, 10, 5, 2],
        }
    )

    out = build_basin_process_summary(
        df=df,
        constituents=["FS", "DIN"],
        value_column="LoadToRegExport (kg)",
    )

    assert "B1" in out
    assert out["B1"]["FS"].loc["Hillslope", "LoadToRegExport (kg)"] == 100
    assert out["B1"]["FS"].loc["Streambank", "LoadToRegExport (kg)"] == 50
    assert out["B1"]["FS"].loc["Gully", "LoadToRegExport (kg)"] == 25
    assert out["B1"]["DIN"].loc["SurfaceRunoff", "LoadToRegExport (kg)"] == 10
    assert out["B1"]["DIN"].loc["Seepage", "LoadToRegExport (kg)"] == 5
    assert out["B1"]["DIN"].loc["PointSource", "LoadToRegExport (kg)"] == 2


def test_aggregate_region_process_summary():
    basin_summary = {
        "B1": {
            "FS": pd.DataFrame({"LoadToRegExport (kg)": [10, 20]}, index=["Hillslope", "Streambank"])
        },
        "B2": {
            "FS": pd.DataFrame({"LoadToRegExport (kg)": [30, 40]}, index=["Hillslope", "Streambank"])
        },
    }

    out = aggregate_region_process_summary(basin_summary, constituents=["FS"])

    assert out["FS"].loc["Hillslope", "LoadToRegExport (kg)"] == 40
    assert out["FS"].loc["Streambank", "LoadToRegExport (kg)"] == 60


def test_aggregate_gbr_process_summary():
    region_summaries = {
        "CY": {"FS": pd.DataFrame({"LoadToRegExport (kg)": [10]}, index=["Hillslope"])},
        "WT": {"FS": pd.DataFrame({"LoadToRegExport (kg)": [20]}, index=["Hillslope"])},
    }

    out = aggregate_gbr_process_summary(region_summaries, constituents=["FS"])

    assert out["FS"].loc["Hillslope", "LoadToRegExport (kg)"] == 30