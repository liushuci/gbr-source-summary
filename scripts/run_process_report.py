
from __future__ import annotations

from pathlib import Path
import argparse

from gbr_source_summary import GBRConfig, run_process_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run GBR process report exports."
    )

    parser.add_argument(
        "--base-path",
        required=True,
        help="Base folder, e.g. F:/RC13_RC2023_24_Gold",
    )
    parser.add_argument(
        "--model",
        default="BASE",
        choices=["PREDEV", "BASE", "CHANGE"],
        help="Scenario/model name.",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Single region code, e.g. CY",
    )
    parser.add_argument(
        "--regions",
        nargs="*",
        default=None,
        help="Optional list of regions, e.g. CY WT BU MW FI BM",
    )
    parser.add_argument(
        "--constituents",
        nargs="*",
        default=None,
        help="Optional list of constituents, e.g. FS PN PP DIN",
    )
    parser.add_argument(
        "--value-column",
        default="LoadToRegExport (kg)",
        help="Value column to summarise.",
    )
    parser.add_argument(
        "--units",
        default="report",
        choices=["kg", "t", "kt", "t/yr", "kt/yr", "report"],
        help="Output units.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output folder. Default: <base-path>/report_card_summary/process",
    )
    parser.add_argument(
        "--no-region-tables",
        action="store_true",
        help="Do not export one CSV per region/constituent.",
    )
    parser.add_argument(
        "--no-combined-tables",
        action="store_true",
        help="Do not export combined constituent CSV tables.",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Do not export Excel workbook.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    cfg = GBRConfig(main_path=Path(args.base_path))

    if args.output_dir is None:
        output_dir = Path(args.base_path) / "report_card_summary" / "process"
    else:
        output_dir = Path(args.output_dir)

    result = run_process_report(
        cfg=cfg,
        output_dir=output_dir,
        model=args.model,
        region=args.region,
        regions=args.regions,
        constituents=args.constituents,
        value_column=args.value_column,
        units=args.units,
        export_region_tables=not args.no_region_tables,
        export_combined_tables=not args.no_combined_tables,
        export_excel_workbook=not args.no_excel,
    )

    print("\nProcess report completed.")
    print(f"Output folder: {output_dir}")

    files = result.get("files", {})
    if files:
        print("\nSaved files:")
        for key, path in files.items():
            print(f"  {key}: {path}")

    combined = result.get("combined", {})
    if combined:
        print("\nPreview of combined process tables:")
        for constituent, df in combined.items():
            print(f"\n[{constituent}]")
            print(df.head())


if __name__ == "__main__":
    main()