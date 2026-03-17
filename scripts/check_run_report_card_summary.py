from pathlib import Path

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.report_card_summary import run_report_card_summary


def main():
    cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))
    out_dir = Path("check_outputs") / "report_card_summary"

    result = run_report_card_summary(
        cfg=cfg,
        output_dir=out_dir,
        constituents=["FS", "PN", "PP", "DIN"],
        units="report",
        process_model="BASE",
    )

    print("=== files ===")
    for k, v in result["files"].items():
        print(f"{k}: {v}")

    print("\n=== gbr_summary head ===")
    print(result["gbr_summary"].head())

    print("\n=== qa_summary ===")
    print(result["qa_summary"].head(20))

    print("\n=== region_summary head ===")
    print(result["region_summary"].head())

    print("\n=== basin_summary head ===")
    print(result["basin_summary"].head())


    print("\n=== qa file ===")
    print(result["files"]["qa_summary_csv"])
    
    print("\n=== all_summary rows ===")
    print(len(result["summary"]))

    print("\n=== levels ===")
    print(result["summary"]["Level"].dropna().unique().tolist())


if __name__ == "__main__":
    main()