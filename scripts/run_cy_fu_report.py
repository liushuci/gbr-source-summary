from pathlib import Path

from gbr_source_summary import GBRConfig
from gbr_source_summary.report_fu import run_fu_report


def main():

    # Location of RC13 Source outputs
    cfg = GBRConfig(
        main_path=Path(r"F:\RC13_RC2023_24_Gold")
    )

    # Output folder
    output_dir = Path(
        r"C:\Users\lius\OneDrive - ITP (Queensland Government)\ShuciL\CY_rebuild\Code\GBR_source_summary\outputs\CY_report"
    )

    result = run_fu_report(
        cfg=cfg,

        # choose region
        region="CY",

        # model scenarios handled internally
        units="report",     # kt/yr sediment, t/yr nutrients

        # export options
        export_region_tables=True,
        export_combined_tables=True,
        export_excel_workbook=True,
        export_qa_workbook=True,

        output_dir=output_dir,
    )

    print("\nReport completed.")
    print("Files written to:")
    print(output_dir)


if __name__ == "__main__":
    main()