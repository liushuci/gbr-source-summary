from pathlib import Path

from gbr_source_summary.config import GBRConfig


def test_config_defaults():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    assert cfg.rc == "Gold_93_23"
    assert "CY" in cfg.regions
    assert cfg.per_year == 1 / 30


def test_region_lut_path():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    expected = Path(r"F:\RC13_RC2023_24_Gold\Regions\CY_Subcat_Regions_LUT.csv")
    assert cfg.get_region_lut_path("CY") == expected


def test_model_output_dir():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    expected = Path(
        r"F:\RC13_RC2023_24_Gold\Gold_ResultsSets_PointOfTruth\CY\Model_Outputs\BASE_Gold_93_23"
    )
    assert cfg.get_model_output_dir("CY", "BASE") == expected