import pandas as pd

from gbr_source_summary.comparison import (
    calc_anthropogenic,
    calc_reduction,
    calc_percent_reduction,
)


def test_fu_comparison_math():
    predev = pd.DataFrame({"FS": [40], "DIN": [10]}, index=["Cropping"])
    base = pd.DataFrame({"FS": [100], "DIN": [50]}, index=["Cropping"])
    change = pd.DataFrame({"FS": [70], "DIN": [20]}, index=["Cropping"])

    anthropogenic = calc_anthropogenic(base, predev)
    reduction = calc_reduction(base, change)
    percent_reduction = calc_percent_reduction(base, predev, change)

    assert anthropogenic.loc["Cropping", "FS"] == 60
    assert reduction.loc["Cropping", "FS"] == 30
    assert round(percent_reduction.loc["Cropping", "FS"], 2) == 50.0