import pandas as pd

from gbr_source_summary.qa_checks import (
    check_no_negative_values,
    check_anthropogenic_consistency,
    check_reduction_consistency,
    check_percent_reduction_bounds,
)


def test_check_no_negative_values():
    df = pd.DataFrame({"FS": [1, -2], "DIN": [3, 4]}, index=["A", "B"])
    out = check_no_negative_values(df)
    assert list(out.index) == ["B"]


def test_check_anthropogenic_consistency():
    base = pd.DataFrame({"FS": [10]}, index=["Cropping"])
    predev = pd.DataFrame({"FS": [4]}, index=["Cropping"])
    anthropogenic = pd.DataFrame({"FS": [6]}, index=["Cropping"])

    out = check_anthropogenic_consistency(base, predev, anthropogenic)
    assert bool(out.loc["Cropping", "within_tolerance"])


def test_check_reduction_consistency():
    base = pd.DataFrame({"FS": [10]}, index=["Cropping"])
    change = pd.DataFrame({"FS": [7]}, index=["Cropping"])
    reduction = pd.DataFrame({"FS": [3]}, index=["Cropping"])

    out = check_reduction_consistency(base, change, reduction)
    assert bool(out.loc["Cropping", "within_tolerance"])


def test_check_percent_reduction_bounds():
    df = pd.DataFrame({"FS": [50, 120]}, index=["A", "B"])
    out = check_percent_reduction_bounds(df)
    assert list(out.index) == ["B"]