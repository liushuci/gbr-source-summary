from pathlib import Path

import pytest

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.regions import resolve_regions


def test_resolve_single_region():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    assert resolve_regions(cfg, region="CY") == ["CY"]


def test_resolve_multiple_regions():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    assert resolve_regions(cfg, regions=["CY", "WT"]) == ["CY", "WT"]


def test_resolve_all_regions():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    assert resolve_regions(cfg) == cfg.regions


def test_resolve_invalid_region():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    with pytest.raises(ValueError):
        resolve_regions(cfg, region="GBR")


def test_resolve_both_region_and_regions():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    with pytest.raises(ValueError):
        resolve_regions(cfg, region="CY", regions=["WT"])