from pathlib import Path

from gbr_source_summary import GBRConfig, run_process_report

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = run_process_report(
    cfg=cfg,
    model="BASE",
    region="CY",
    output_dir=Path("outputs") / "CY_process_report",
    units="report",
)

print("\nProcess report completed.")
print("Output folder: outputs/CY_process_report")

print("\nCombined FS process table:")
print(result["combined"]["FS"].head())