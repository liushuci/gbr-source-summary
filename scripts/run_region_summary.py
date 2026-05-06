from __future__ import annotations

from pathlib import Path
import argparse

import pandas as pd

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.workflows_region import build_region_scenario_comparison
from gbr_source_summary.naming import (
    standardise_constituent_names,
    standardise_management_unit_names,
)
from gbr_source_summary.export_excel import export_tables_to_excel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build GBR region-scale scenario summaries."
    )

    parser.add_argument(
        "--base-path",
        required=True,
        help="Base folder, e.g. F:/RC13_RC2023_24_Gold",
    )
    parser.add_argument(
        "--basin-scale",
        default="48",
        choices=["35", "48", "Basin_35", "MU_48", "Manag_Unit_48"],
        help="Basin aggregation scale used before rolling up to region.",
    )
    parser.add_argument(
        "--reporting-units",
        default="raw",
        choices=["raw", "report_card"],
        help="Output units: raw kg totals or report card annual units.",
    )
    parser.add_argument(
        "--output-folder",
        default=None,
        help=(
            "Output folder. Defaults to "
            "<repo>/check_outputs/region_summary/<scale>/<units>"
        ),
    )
    parser.add_argument(
        "--value-column",
        default="LoadToRegExport (kg)",
        help="Value column to aggregate.",
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
        help="Optional list of constituents.",
    )
    parser.add_argument(
        "--export-excel",
        action="store_true",
        help="Also export a consolidated Excel workbook.",
    )
    parser.add_argument(
        "--excel-path",
        default=None,
        help="Optional output Excel file path. Used only when --export-excel is set.",
    )

    return parser.parse_args()


def resolve_scale_label(basin_scale: str) -> str:
    basin_scale_lower = basin_scale.strip().lower()
    if basin_scale_lower in {"35", "basin_35"}:
        return "Basin_35"
    return "Manag_Unit_48"


def resolve_metric_label(value_column: str) -> str:
    if "LoadToStream" in value_column:
        return "generated"
    if "LoadToRegExport" in value_column:
        return "exported"
    return "value"


def wide_to_long_with_units(
    df: pd.DataFrame,
    value_name: str,
    reporting_units: str,
    model_years: int,
) -> pd.DataFrame:
    """
    Convert wide comparison dataframe back to long format with units.
    """
    out = df.reset_index().melt(
        id_vars=["Region"],
        var_name="Constituent",
        value_name=value_name,
    )

    if value_name == "PercentReduction":
        out["Units"] = "%"
        out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
        return out

    if reporting_units == "report_card":
        out["Units"] = "t/yr"
        fs_mask = out["Constituent"] == "FS"
        out.loc[fs_mask, "Units"] = "kt/yr"

        out[value_name] = pd.to_numeric(out[value_name], errors="coerce").fillna(0.0)
        out.loc[fs_mask, value_name] = (
            out.loc[fs_mask, value_name] / 1e6 / model_years
        )
        out.loc[~fs_mask, value_name] = (
            out.loc[~fs_mask, value_name] / 1e3 / model_years
        )
    else:
        out["Units"] = "kg"
        out[value_name] = pd.to_numeric(out[value_name], errors="coerce").fillna(0.0)

    return out


def main() -> None:
    args = parse_args()

    base_path = Path(args.base_path)
    repo_root = Path(__file__).resolve().parents[1]

    basin_scale_label = resolve_scale_label(args.basin_scale)
    metric_label = resolve_metric_label(args.value_column)

    if args.output_folder is None:
        output_folder = (
            repo_root
            / "check_outputs"
            / "region_summary"
            / basin_scale_label
            / args.reporting_units
        )

        if args.regions is not None:
            if len(args.regions) == 1:
                region_label = args.regions[0]
            elif len(args.regions) > 1:
                region_label = f"{len(args.regions)}regions_" + "_".join(args.regions)
            else:
                region_label = None

            if region_label is not None:
                output_folder = output_folder / region_label
    else:
        output_folder = Path(args.output_folder)

    output_folder.mkdir(parents=True, exist_ok=True)

    print(f"Base path       : {base_path}")
    print(f"Basin scale     : {args.basin_scale}")
    print(f"Reporting units : {args.reporting_units}")
    print(f"Output folder   : {output_folder}")
    print(f"Metric type     : {metric_label}")
    print(f"Value column    : {args.value_column}")
    print(f"Regions filter  : {args.regions}")
    print(f"Constituents    : {args.constituents}")

    cfg = GBRConfig(
        main_path=base_path,
    )

    outputs = build_region_scenario_comparison(
        cfg=cfg,
        basin_scale=args.basin_scale,
        regions=args.regions,
        constituents=args.constituents,
        value_column=args.value_column,
        reporting_units=args.reporting_units,
    )

    anthropogenic_long = wide_to_long_with_units(
        outputs["anthropogenic"],
        value_name="RegionAnthropogenic",
        reporting_units=args.reporting_units,
        model_years=cfg.model_years,
    )
    reduction_long = wide_to_long_with_units(
        outputs["reduction"],
        value_name="RegionReduction",
        reporting_units=args.reporting_units,
        model_years=cfg.model_years,
    )
    percent_reduction_long = wide_to_long_with_units(
        outputs["percent_reduction"],
        value_name="PercentReduction",
        reporting_units=args.reporting_units,
        model_years=cfg.model_years,
    )

    run_label = cfg.rc

    out_region_totals = output_folder / f"region_totals_{metric_label}_{run_label}.csv"
    out_base = output_folder / f"region_base_wide_{metric_label}_{run_label}.csv"
    out_predev = output_folder / f"region_predev_wide_{metric_label}_{run_label}.csv"
    out_change = output_folder / f"region_change_wide_{metric_label}_{run_label}.csv"
    out_anth = (
        output_folder / f"region_anthropogenic_{metric_label}_{run_label}.csv"
    )
    out_red = output_folder / f"region_reduction_{metric_label}_{run_label}.csv"
    out_pct = (
        output_folder / f"region_percent_reduction_{metric_label}_{run_label}.csv"
    )

    if args.excel_path is None:
        out_excel = output_folder / f"region_summary_{metric_label}_{run_label}.xlsx"
    else:
        out_excel = Path(args.excel_path)

    value_column = args.value_column
    clean_value_column = value_column.replace(" (kg)", "").replace("(kg)", "").strip()

    outputs["region_totals"] = outputs["region_totals"].rename(
        columns={value_column: clean_value_column}
    )

    # Standardise constituent names
    outputs["region_totals"]["Constituent"] = standardise_constituent_names(
        outputs["region_totals"]["Constituent"]
    )
    anthropogenic_long["Constituent"] = standardise_constituent_names(
        anthropogenic_long["Constituent"]
    )
    reduction_long["Constituent"] = standardise_constituent_names(
        reduction_long["Constituent"]
    )
    percent_reduction_long["Constituent"] = standardise_constituent_names(
        percent_reduction_long["Constituent"]
    )

    # Standardise region names if needed later; for now keep Region unchanged.
    # Basin naming is not used in final region outputs, but basin_totals can still be cleaned if exported later.
    outputs["basin_totals"]["Basin"] = standardise_management_unit_names(
        outputs["basin_totals"]["Basin"]
    )

    outputs["region_totals"].to_csv(out_region_totals, index=False)
    outputs["base_wide"].to_csv(out_base)
    outputs["predev_wide"].to_csv(out_predev)
    outputs["change_wide"].to_csv(out_change)
    anthropogenic_long.to_csv(out_anth, index=False)
    reduction_long.to_csv(out_red, index=False)
    percent_reduction_long.to_csv(out_pct, index=False)

    if args.export_excel:
        excel_tables = {
            "region_totals": outputs["region_totals"],
            "region_base_wide": outputs["base_wide"].reset_index(),
            "region_predev_wide": outputs["predev_wide"].reset_index(),
            "region_change_wide": outputs["change_wide"].reset_index(),
            "region_anthropogenic": anthropogenic_long,
            "region_reduction": reduction_long,
            "region_percent_reduction": percent_reduction_long,
        }

        export_tables_to_excel(
            tables=excel_tables,
            output_path=out_excel,
            index=False,
        )

    print("\nSaved outputs:")
    print(f"  {out_region_totals}")
    print(f"  {out_base}")
    print(f"  {out_predev}")
    print(f"  {out_change}")
    print(f"  {out_anth}")
    print(f"  {out_red}")
    print(f"  {out_pct}")
    if args.export_excel:
        print(f"  {out_excel}")

    print("\nPreview: region_totals")
    print(outputs["region_totals"].head())

    print("\nPreview: region_anthropogenic")
    print(anthropogenic_long.head())

    print("\nPreview: region_percent_reduction")
    print(percent_reduction_long.head())


if __name__ == "__main__":
    main()