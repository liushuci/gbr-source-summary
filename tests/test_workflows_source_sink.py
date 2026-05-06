from __future__ import annotations

import pandas as pd

from gbr_source_summary.workflows_source_sink import (
    build_basin_source_sink_summary_from_raw,
    build_region_source_sink_summary,
    build_gbr_source_sink_summary,
    convert_source_sink_to_annual_units,
    summarise_basin_budget_for_constituent,
)


def test_summarise_basin_budget_for_FS_cy_keeps_undefined_separate() -> None:
    df = pd.DataFrame(
        {
            "BudgetElement": [
                "Hillslope",
                "Undefined",
                "Streambank",
                "Gully",
                "Channel Remobilisation",
                "Extraction",
                "Node Loss",
                "Residual Link Storage",
                "Residual Node Storage",
                "Flood Plain Deposition",
                "Reservoir Deposition",
                "Stream Deposition",
            ],
            "Total_Load_in_Kg": [
                100.0,
                50.0,
                20.0,
                30.0,
                40.0,
                1.0,
                2.0,
                3.0,
                4.0,
                5.0,
                6.0,
                7.0,
            ],
        }
    )

    out = summarise_basin_budget_for_constituent(
        df_basin_constituent=df,
        constituent="FS",
        region="CY",
    )

    result = dict(zip(out["BudgetGroup"], out["Total_Load_in_Kg"]))

    assert result["Hillslope"] == 100.0
    assert result["Streambank"] == 20.0
    assert result["Gully"] == 30.0
    assert result["ChannelRemobilisation"] == 40.0
    assert result["Extraction + Other Minor Losses"] == 10.0
    assert result["FloodPlainDeposition"] == 5.0
    assert result["ReservoirDeposition"] == 6.0
    assert result["StreamDeposition"] == 7.0


def test_summarise_basin_budget_for_FS_wt_adds_undefined_to_hillslope() -> None:
    df = pd.DataFrame(
        {
            "BudgetElement": ["Hillslope", "Undefined"],
            "Total_Load_in_Kg": [100.0, 50.0],
        }
    )

    out = summarise_basin_budget_for_constituent(
        df_basin_constituent=df,
        constituent="FS",
        region="WT",
    )

    result = dict(zip(out["BudgetGroup"], out["Total_Load_in_Kg"]))
    assert result["Hillslope"] == 150.0


def test_summarise_basin_budget_for_pn_adds_undefined_to_hillslope() -> None:
    df = pd.DataFrame(
        {
            "BudgetElement": ["Hillslope", "Undefined"],
            "Total_Load_in_Kg": [10.0, 5.0],
        }
    )

    out = summarise_basin_budget_for_constituent(
        df_basin_constituent=df,
        constituent="PN",
        region="CY",
    )

    result = dict(zip(out["BudgetGroup"], out["Total_Load_in_Kg"]))
    assert result["Hillslope"] == 15.0


def test_summarise_basin_budget_for_din_cy_surface_runoff() -> None:
    df = pd.DataFrame(
        {
            "BudgetElement": [
                "Diffuse Dissolved",
                "Hillslope",
                "Undefined",
                "Seepage",
                "Point Source",
                "Extraction",
                "Node Loss",
                "Residual Link Storage",
                "Residual Node Storage",
            ],
            "Total_Load_in_Kg": [10.0, 20.0, 30.0, 5.0, 6.0, 1.0, 2.0, 3.0, 4.0],
        }
    )

    out = summarise_basin_budget_for_constituent(
        df_basin_constituent=df,
        constituent="DIN",
        region="CY",
    )

    result = dict(zip(out["BudgetGroup"], out["Total_Load_in_Kg"]))

    assert result["SurfaceRunoff"] == 30.0
    assert result["Seepage"] == 5.0
    assert result["PointSource"] == 6.0
    assert result["Extraction + Other Minor Losses"] == 10.0


def test_summarise_basin_budget_for_din_fi_surface_runoff() -> None:
    df = pd.DataFrame(
        {
            "BudgetElement": ["Diffuse Dissolved", "Hillslope", "Undefined"],
            "Total_Load_in_Kg": [10.0, 20.0, 30.0],
        }
    )

    out = summarise_basin_budget_for_constituent(
        df_basin_constituent=df,
        constituent="DIN",
        region="FI",
    )

    result = dict(zip(out["BudgetGroup"], out["Total_Load_in_Kg"]))
    assert result["SurfaceRunoff"] == 10.0


def test_build_basin_source_sink_summary_from_raw_standardises_names() -> None:
    raw = pd.DataFrame(
        {
            "Manag_Unit_48": ["Normanby River", "Normanby River"],
            "Constituent": ["Sediment - Fine", "Sediment - Fine"],
            "BudgetElement": ["Hillslope", "Streambank"],
            "Total_Load_in_Kg": [1000.0, 500.0],
        }
    )

    out = build_basin_source_sink_summary_from_raw(
        raw_results=raw,
        region="CY",
        scenario="BASE",
        basin_column="Manag_Unit_48",
        constituent_column="Constituent",
        budget_element_column="BudgetElement",
        value_column="Total_Load_in_Kg",
    )

    assert set(out["Region"]) == {"CY"}
    assert set(out["Scenario"]) == {"BASE"}
    assert set(out["Basin"]) == {"Normanby"}
    assert set(out["Constituent"]) == {"FS"}
    assert set(out["Units"]) == {"kg"}


def test_build_region_source_sink_summary_sums_basins() -> None:
    basin_df = pd.DataFrame(
        {
            "Region": ["CY", "CY", "CY"],
            "Scenario": ["BASE", "BASE", "BASE"],
            "Basin": ["Normanby", "Endeavour", "Normanby"],
            "Constituent": ["DIN", "DIN", "DIN"],
            "BudgetGroup": ["SurfaceRunoff", "SurfaceRunoff", "PointSource"],
            "Total_Load_in_Kg": [100.0, 50.0, 20.0],
            "Units": ["kg", "kg", "kg"],
        }
    )

    out = build_region_source_sink_summary(
        basin_source_sink=basin_df,
        scenario="BASE",
        value_column="Total_Load_in_Kg",
    )

    runoff = out.loc[
        (out["Region"] == "CY")
        & (out["Constituent"] == "DIN")
        & (out["BudgetGroup"] == "SurfaceRunoff"),
        "Total_Load_in_Kg",
    ].iloc[0]

    point = out.loc[
        (out["Region"] == "CY")
        & (out["Constituent"] == "DIN")
        & (out["BudgetGroup"] == "PointSource"),
        "Total_Load_in_Kg",
    ].iloc[0]

    assert runoff == 150.0
    assert point == 20.0


def test_build_gbr_source_sink_summary_sums_regions() -> None:
    region_df = pd.DataFrame(
        {
            "Region": ["CY", "WT"],
            "Scenario": ["BASE", "BASE"],
            "Constituent": ["DIN", "DIN"],
            "BudgetGroup": ["SurfaceRunoff", "SurfaceRunoff"],
            "Total_Load_in_Kg": [100.0, 200.0],
            "Units": ["kg", "kg"],
        }
    )

    out = build_gbr_source_sink_summary(
        region_source_sink=region_df,
        value_column="Total_Load_in_Kg",
    )

    total = out.loc[
        (out["Scenario"] == "BASE")
        & (out["Constituent"] == "DIN")
        & (out["BudgetGroup"] == "SurfaceRunoff"),
        "Total_Load_in_Kg",
    ].iloc[0]

    assert total == 300.0


def test_convert_source_sink_to_annual_units() -> None:
    df = pd.DataFrame(
        {
            "Constituent": ["FS", "DIN"],
            "Total_Load_in_Kg": [3_000_000.0, 30_000.0],
        }
    )

    out = convert_source_sink_to_annual_units(
        df=df,
        model_years=30.0,
        value_column="Total_Load_in_Kg",
    )

    FS_val = out.loc[out["Constituent"] == "FS", "Total_Load_in_Kg"].iloc[0]
    din_val = out.loc[out["Constituent"] == "DIN", "Total_Load_in_Kg"].iloc[0]

    FS_unit = out.loc[out["Constituent"] == "FS", "Units"].iloc[0]
    din_unit = out.loc[out["Constituent"] == "DIN", "Units"].iloc[0]

    assert FS_val == 0.1
    assert din_val == 1.0
    assert FS_unit == "kt/yr"
    assert din_unit == "t/yr"