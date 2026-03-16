from pathlib import Path

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.report_fu import run_all_gbr_fu_reports


def main():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    out_dir = Path("check_outputs") / "fu_all_regions"

    result = run_all_gbr_fu_reports(
        cfg=cfg,
        output_dir=out_dir,
        constituents=["FS", "PN", "PP", "DIN"],
        value_column="LoadToRegExport (kg)",
        units="report",
    )

    print("regions_run:", result["regions_run"])
    print("result keys:", list(result.keys()))
    print("qa keys:", list(result.get("qa", {}).keys()))

    for key in ["predev", "base", "change", "anthropogenic", "reduction", "percent_reduction"]:
        print(f"\n=== {key} ===")
        print(result[key].head())


if __name__ == "__main__":
    main()