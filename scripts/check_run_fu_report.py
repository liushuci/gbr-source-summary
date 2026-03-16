from pathlib import Path

from gbr_source_summary import GBRConfig, run_fu_report

cfg = GBRConfig(main_path=Path(r"F:\RC13_RC2023_24_Gold"))

result = run_fu_report(
    cfg=cfg,
    region="CY",
    output_dir=Path("outputs") / "CY_report",
    units="report",
)

print("\nReport completed.")
print("Output folder: outputs/CY_report")
print("\nBase table preview:")
print(result["base"].head())

print("\nQA sheets generated:")
for name in result.get("qa", {}):
    print("-", name)