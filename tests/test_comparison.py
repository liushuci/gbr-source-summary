import pandas as pd

from gbr_source_summary.comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)


def test_calc_anthropogenic():
    base = pd.DataFrame({"FS": [100], "DIN": [50]}, index=["Cropping"])
    predev = pd.DataFrame({"FS": [40], "DIN": [10]}, index=["Cropping"])

    out = calc_anthropogenic(base, predev)

    assert out.loc["Cropping", "FS"] == 60
    assert out.loc["Cropping", "DIN"] == 40


def test_calc_reduction():
    base = pd.DataFrame({"FS": [100], "DIN": [50]}, index=["Cropping"])
    change = pd.DataFrame({"FS": [70], "DIN": [20]}, index=["Cropping"])

    out = calc_reduction(base, change)

    assert out.loc["Cropping", "FS"] == 30
    assert out.loc["Cropping", "DIN"] == 30


def test_calc_percent_reduction():
    base = pd.DataFrame({"FS": [100], "DIN": [50]}, index=["Cropping"])
    predev = pd.DataFrame({"FS": [40], "DIN": [10]}, index=["Cropping"])
    change = pd.DataFrame({"FS": [70], "DIN": [20]}, index=["Cropping"])

    out = calc_percent_reduction(base, predev, change)

    # FS: (100 - 70) / (100 - 40) * 100 = 50
    # DIN: (50 - 20) / (50 - 10) * 100 = 75
    assert round(out.loc["Cropping", "FS"], 2) == 50.0
    assert round(out.loc["Cropping", "DIN"], 2) == 75.0