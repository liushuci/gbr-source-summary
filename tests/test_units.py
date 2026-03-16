import pandas as pd

from gbr_source_summary.units import apply_units, convert_report_units


def test_convert_report_units():
    df = pd.DataFrame(
        {
            "FS": [30_000_000],   # 30,000,000 kg over 30 years = 1 kt/yr
            "DIN": [90_000],      # 90,000 kg over 30 years = 3 t/yr
            "PN": [30_000],       # 30,000 kg over 30 years = 1 t/yr
        },
        index=["Cropping"],
    )

    out = convert_report_units(df, years=30)

    assert round(out.loc["Cropping", "FS"], 4) == 1.0
    assert round(out.loc["Cropping", "DIN"], 4) == 3.0
    assert round(out.loc["Cropping", "PN"], 4) == 1.0


def test_apply_units_report():
    df = pd.DataFrame({"FS": [30_000_000], "DIN": [90_000]}, index=["Cropping"])
    out = apply_units(df, units="report", years=30)

    assert round(out.loc["Cropping", "FS"], 4) == 1.0
    assert round(out.loc["Cropping", "DIN"], 4) == 3.0


def test_convert_report_units_with_flow():
    df = pd.DataFrame(
        {
            "Flow": [3000],        # 3000 ML over 30 years = 0.1 GL/yr
            "FS": [30_000_000],    # 1 kt/yr
            "DIN": [90_000],       # 3 t/yr
        },
        index=["Catchment"],
    )

    out = convert_report_units(df, years=30)

    assert round(out.loc["Catchment", "Flow"], 4) == 0.1
    assert round(out.loc["Catchment", "FS"], 4) == 1.0
    assert round(out.loc["Catchment", "DIN"], 4) == 3.0