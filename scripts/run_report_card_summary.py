"""
Master runner for gbr_source_summary report-card outputs.

This runner creates a full report-card bundle and optionally runs:
- region summary
- basin summary
- subcatchment summary
- landuse / rainfall summary
- source-sink summary
- source-sink sankey
- FU load summary
- process contribution plots
- change summary plots

Process contribution plots are handled inside run_report_card_bundle()
and are written to:

    09_process_contribution_plots

Change summary plots are handled as an extra workflow step and are written to:

    10_change_summary_plots

Notes
-----
- Fine sediment is FS. Do not use TSS.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

from gbr_source_summary.config import GBRConfig
from gbr_source_summary.report_card_summary import run_report_card_bundle


def _maybe_list(value: str | None) -> list[str] | None:
    """
    Convert comma-separated CLI text to a list.

    Example
    -------
    "CY,WT,BU" -> ["CY", "WT", "BU"]
    """
    if value is None:
        return None

    items = [
        x.strip().upper()
        for x in value.split(",")
        if x.strip()
    ]

    return items or None


def _set_cfg_attr_if_present(
    cfg: GBRConfig,
    name: str,
    value: Any,
) -> None:
    """
    Set a GBRConfig attribute only when it exists and value is not None.
    """
    if value is None:
        return

    if hasattr(cfg, name):
        setattr(cfg, name, value)


def _call_with_supported_kwargs(
    func: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    """
    Call a function with only the kwargs it supports.
    """
    sig = inspect.signature(func)

    if any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    ):
        return func(**kwargs)

    accepted = {
        name: value
        for name, value in kwargs.items()
        if name in sig.parameters
    }

    return func(**accepted)


def _resolve_callable(
    module_name: str,
    candidate_names: list[str],
) -> Callable[..., Any]:
    """
    Import a module and return the first available callable.
    """
    module = importlib.import_module(module_name)

    for name in candidate_names:
        fn = getattr(module, name, None)

        if callable(fn):
            return fn

    raise NotImplementedError(
        f"No callable found in {module_name}. "
        f"Tried: {', '.join(candidate_names)}"
    )


def _build_reflective_step(
    *,
    module_name: str,
    candidate_names: list[str],
    extra_kwargs: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """
    Create a lazy extra-step runner for run_report_card_bundle().
    """
    extra_kwargs = extra_kwargs or {}

    def _runner(
        *,
        cfg: GBRConfig,
        output_dir: Path,
        constituents: list[str] | None = None,
        value_column: str = "LoadToRegExport (kg)",
        units: str = "report",
        process_model: str = "BASE",
        bundle_dirs: dict[str, Path] | None = None,
    ) -> Any:

        func = _resolve_callable(
            module_name,
            candidate_names,
        )

        call_kwargs = {
            "cfg": cfg,
            "output_dir": output_dir,
            "output_root": output_dir,
            "out_dir": output_dir,
            "constituents": constituents,
            "value_column": value_column,
            "units": units,
            "process_model": process_model,
            "model": process_model,
            "scenario": process_model,
            "regions": getattr(cfg, "regions", None),
            "bundle_dirs": bundle_dirs,
        }
        call_kwargs.update(extra_kwargs)

        return _call_with_supported_kwargs(
            func,
            **call_kwargs,
        )

    return _runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run full report-card summary bundle."
    )

    parser.add_argument(
        "--main-path",
        type=str,
        required=True,
        help="Main model/data path, e.g. F:/RC13_RC2023_24_Gold.",
    )

    parser.add_argument(
        "--output-root",
        type=str,
        required=True,
        help="Top-level output folder for the report-card bundle.",
    )

    parser.add_argument(
        "--constituents",
        type=str,
        default="FS,PN,PP,DIN",
        help=(
            "Comma-separated constituent list, e.g. "
            "FS,CS,PN,PP,DIN,DON,DIP,DOP. "
            "Fine sediment must be FS, not TSS."
        ),
    )

    parser.add_argument(
        "--regions",
        type=str,
        default=None,
        help="Comma-separated region list, e.g. CY,WT,BU,MW,FI,BM.",
    )

    parser.add_argument(
        "--value-column",
        type=str,
        default="LoadToRegExport (kg)",
        help="Value column to summarise.",
    )

    parser.add_argument(
        "--units",
        type=str,
        default="report",
        choices=[
            "kg",
            "t",
            "kt",
            "t/yr",
            "kt/yr",
            "report",
        ],
        help="Units mode used by package functions.",
    )

    parser.add_argument(
        "--process-model",
        type=str,
        default="BASE",
        choices=[
            "PREDEV",
            "BASE",
            "CHANGE",
        ],
        help="Process model to use for process summaries and plots.",
    )

    parser.add_argument(
        "--model-years",
        type=int,
        default=None,
        help="Override cfg.model_years if needed.",
    )

    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Disable Excel workbook export for the core report-card summary.",
    )

    parser.add_argument(
        "--skip-process-plots",
        action="store_true",
        help=(
            "Skip process contribution tonnage and percent plots. "
            "If not set, plots are written to 09_process_contribution_plots."
        ),
    )

    parser.add_argument(
        "--skip-change-plots",
        action="store_true",
        help=(
            "Skip change summary plots. "
            "If not set, plots are written to 10_change_summary_plots."
        ),
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately if any step fails.",
    )

    parser.add_argument(
        "--skip-region",
        action="store_true",
        help="Skip region summary step.",
    )

    parser.add_argument(
        "--skip-basin",
        action="store_true",
        help="Skip basin summary step.",
    )

    parser.add_argument(
        "--skip-subcatchment",
        action="store_true",
        help="Skip subcatchment summary step.",
    )

    parser.add_argument(
        "--skip-landuse",
        action="store_true",
        help="Skip landuse/rainfall step.",
    )

    parser.add_argument(
        "--skip-source-sink",
        action="store_true",
        help="Skip source-sink summary step.",
    )

    parser.add_argument(
        "--skip-sankey",
        action="store_true",
        help="Skip source-sink sankey step.",
    )

    parser.add_argument(
        "--skip-fu-load",
        action="store_true",
        help="Skip FU load/areal summary step.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    constituents = _maybe_list(args.constituents)
    regions = _maybe_list(args.regions)

    if constituents and "TSS" in constituents:
        raise ValueError(
            "TSS is not supported in this package runner. "
            "Use FS for fine sediment."
        )

    cfg = GBRConfig(
        main_path=args.main_path,
    )

    _set_cfg_attr_if_present(
        cfg,
        "regions",
        regions,
    )

    _set_cfg_attr_if_present(
        cfg,
        "model_years",
        args.model_years,
    )

    extra_steps: dict[str, Callable[..., Any]] = {}

    if not args.skip_region:
        extra_steps["region_summary"] = _build_reflective_step(
            module_name="gbr_source_summary.workflows_region",
            candidate_names=[
                "run_region_summary",
                "build_region_summary",
                "export_region_summary",
            ],
        )

    if not args.skip_basin:
        extra_steps["basin_summary"] = _build_reflective_step(
            module_name="gbr_source_summary.workflows_basin",
            candidate_names=[
                "run_basin_summary",
                "build_basin_summary",
                "export_basin_summary",
            ],
        )

    if not args.skip_subcatchment:
        extra_steps["subcatchment_summary"] = _build_reflective_step(
            module_name="gbr_source_summary.report_subcatchment_summary",
            candidate_names=[
                "run_subcatchment_summary",
                "build_subcatchment_summary",
                "export_subcatchment_summary",
            ],
        )

    if not args.skip_landuse:
        extra_steps["landuse_rainfall"] = _build_reflective_step(
            module_name="gbr_source_summary.workflows_landuse_rainfall",
            candidate_names=[
                "run_landuse_rainfall_summary",
                "build_landuse_rainfall_summary",
                "export_landuse_rainfall_summary",
            ],
        )

    if not args.skip_source_sink:
        extra_steps["source_sink_summary"] = _build_reflective_step(
            module_name="gbr_source_summary.workflows_source_sink",
            candidate_names=[
                "run_source_sink_summary",
                "build_source_sink_summary",
                "export_source_sink_summary",
            ],
        )

    if not args.skip_sankey:
        extra_steps["source_sink_sankey"] = _build_reflective_step(
            module_name="gbr_source_summary.run_sankey_for_all_basins",
            candidate_names=[
                "run_source_sink_sankey_for_all_basins",
                "run_source_sink_sankey_all_basins",
                "export_source_sink_sankey_all_basins",
            ],
            extra_kwargs={
                "base_path": Path(args.main_path),
                "main_path": Path(args.main_path),
                "source_sink_dir": Path(args.output_root) / "06_source_sink_summary",
                "basin_scale": "MU48",
            },
        )

    if not args.skip_fu_load:
        extra_steps["fu_load_summary"] = _build_reflective_step(
            module_name="gbr_source_summary.report_card_summary",
            candidate_names=[
                "run_fu_load_summary",
            ],
        )

    if not args.skip_change_plots:
        extra_steps["change_summary_plots"] = _build_reflective_step(
            module_name="gbr_source_summary.workflows_change_summary_plots",
            candidate_names=[
                "run_change_summary_plots",
            ],
        )

    result = run_report_card_bundle(
        cfg=cfg,
        output_root=Path(args.output_root),
        constituents=constituents,
        value_column=args.value_column,
        units=args.units,
        process_model=args.process_model,
        export_excel_workbook=not args.no_excel,
        extra_steps=extra_steps,
        fail_fast=args.fail_fast,
        make_process_contribution_plots=not args.skip_process_plots,
    )

    print("\n=== Report-card bundle complete ===")
    print(f"Output root: {result['output_root']}")

    print("\nSettings:")
    print(
        "  Regions                   : "
        f"{', '.join(regions) if regions else 'cfg.regions'}"
    )
    print(
        "  Constituents              : "
        f"{', '.join(constituents) if constituents else 'default'}"
    )
    print(f"  Units                     : {args.units}")
    print(f"  Process model             : {args.process_model}")
    print(f"  Excel export              : {'no' if args.no_excel else 'yes'}")
    print(
        "  Process contribution plots: "
        f"{'no' if args.skip_process_plots else 'yes'}"
    )
    print(
        "  Change summary plots      : "
        f"{'no' if args.skip_change_plots else 'yes'}"
    )

    print("\nExpected subcatchment summary folder:")
    print(
        Path(args.output_root)
        / "04_subcatchment_summary"
    )

    print("\nExpected process plot folder:")
    print(
        Path(args.output_root)
        / "09_process_contribution_plots"
    )

    print("\nExpected change summary plot folder:")
    print(
        Path(args.output_root)
        / "10_change_summary_plots"
    )

    print("\nStep summary:")
    print(
        result["step_summary"].to_string(
            index=False,
        )
    )


if __name__ == "__main__":
    main()