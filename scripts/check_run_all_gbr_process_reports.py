from pathlib import Path

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.report_process import run_all_gbr_process_reports


def main():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    out_dir = Path("check_outputs") / "process_all_regions"

    result = run_all_gbr_process_reports(
        cfg=cfg,
        output_dir=out_dir,
        model="BASE",
        constituents=["FS", "PN", "PP", "DIN"],
        value_column="LoadToRegExport (kg)",
        units="report",
    )

    print("regions_run:", result["regions_run"])
    print("result keys:", list(result.keys()))
    print("combined constituents:", list(result["combined"].keys()))

    for constituent, df in result["combined"].items():
        print(f"\n=== {constituent} ===")
        print(df.head())


if __name__ == "__main__":
    main()