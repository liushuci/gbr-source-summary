from pathlib import Path

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.summary_flow import aggregate_flow_tables
from gbr_source_summary.regions import resolve_regions


def test_resolve_regions_for_flow_single():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    assert resolve_regions(cfg, region="CY") == ["CY"]


def test_aggregate_flow_tables():
    tables = {
        "CY": __import__("pandas").DataFrame({"Value": [10]}, index=["Cropping"]),
        "WT": __import__("pandas").DataFrame({"Value": [20]}, index=["Cropping"]),
    }

    out = aggregate_flow_tables(tables)
    assert out.loc["Cropping", "Value"] == 30