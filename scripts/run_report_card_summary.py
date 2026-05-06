"""
Master runner for gbr_source_summary report-card outputs.

What this does
--------------
1. Creates one clean output root
2. Runs the core report-card summary
3. Tries to run additional workflows one by one:
   - region summary
   - basin summary
   - landuse / rainfall summary
   - source-sink summary
   - source-sink sankey

This runner is intentionally defensive:
- it tries several candidate function names per module
- it passes only supported kwargs using function signature inspection
- if a workflow is not yet wired, it is marked as SKIPPED instead of crashing
  unless --fail-fast is used
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
    if value is None:
        return None
    items = [x.strip() for x in value.split(",") if x.strip()]
    return items or None


def _set_cfg_attr_if_present(cfg: GBRConfig, name: str, value: Any) -> None:
    if value is None:
        return
    if hasattr(cfg, name):
        setattr(cfg, name, value)


def _call_with_supported_kwargs(func: Callable[..., Any], **kwargs: Any) -> Any:
    sig = inspect.signature(func)
    accepted = {
        name: value
        for name, value in kwargs.items()
        if name in sig.parameters
    }
    return func(**accepted)


def _resolve_callable(module_name: str, candidate_names: list[str]) -> Callable[..., Any]:
    module = importlib.import_module(module_name)

    for name in candidate_names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn

    raise NotImplementedError(
        f"No callable found in {module_name}. Tried: {', '.join(candidate_names)}"
    )


def _build_reflective_step(
    *,
    module_name: str,
    candidate_names: list[str],
    extra_kwargs: dict[str, Any] | None = None,
) -> Callable[..., Any]:
    """
    Return a callable compatible with run_report_card_bundle(extra_steps=...).

    It imports the target module lazily and tries the provided candidate
    function names in order.
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
        func = _resolve_callable(module_name, candidate_names)

        return _call_with_supported_kwargs(
            func,
            cfg=cfg,
            output_dir=output_dir,
            output_root=output_dir,
            out_dir=output_dir,
            constituents=constituents,
            value_column=value_column,
            units=units,
            process_model=process_model,
            model=process_model,
            regions=getattr(cfg, "regions", None),
            bundle_dirs=bundle_dirs,
            **extra_kwargs,
        )

    return _runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full report-card summary bundle.")

    parser.add_argument(
        "--main-path",
        type=str,
        default=None,
        help="Main model/data path passed into GBRConfig if supported.",
    )
    parser.add_argument(
        "--output-root",
        type=str,
        required=True,
        help="Top-level output folder for the whole report-card bundle.",
    )
    parser.add_argument(
        "--constituents",
        type=str,
        default=None,
        help="Comma-separated constituent list, e.g. FS,DIN,PN,PP",
    )
    parser.add_argument(
        "--regions",
        type=str,
        default=None,
        help="Comma-separated region list, e.g. CY,WT,BU,MW,FI,BM",
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
        help="Units mode used by package functions.",
    )
    parser.add_argument(
        "--process-model",
        type=str,
        default="BASE",
        help="Process model to use for process summaries.",
    )
    parser.add_argument(
        "--model-years",
        type=float,
        default=None,
        help="Override cfg.model_years if needed.",
    )
    parser.add_argument(
        "--no-excel",
        action="store_true",
        help="Disable Excel workbook export for the core report-card summary.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop immediately if any step fails.",
    )

    # Step toggles
    parser.add_argument("--skip-region", action="store_true", help="Skip region summary step.")
    parser.add_argument("--skip-basin", action="store_true", help="Skip basin summary step.")
    parser.add_argument("--skip-landuse", action="store_true", help="Skip landuse/rainfall step.")
    parser.add_argument("--skip-source-sink", action="store_true", help="Skip source-sink summary step.")
    parser.add_argument("--skip-sankey", action="store_true", help="Skip source-sink sankey step.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    constituents = _maybe_list(args.constituents)
    regions = _maybe_list(args.regions)

    # Build config
    if args.main_path is not None:
        cfg = GBRConfig(main_path=args.main_path)
    else:
        cfg = GBRConfig()

    _set_cfg_attr_if_present(cfg, "regions", regions)
    _set_cfg_attr_if_present(cfg, "model_years", args.model_years)

    extra_steps: dict[str, Callable[..., Any]] = {}

    if not args.skip_region:
        extra_steps["region_summary"] = _build_reflective_step(
            module_name="gbr_source_summary.workflows_region",
            candidate_names=[
                "run_region_summary",
                # "build_region_summary",
                # "export_region_summary",
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
            module_name="gbr_source_summary.workflows_source_sink",
            candidate_names=[
                "run_source_sink_sankey_all_basins",
                "run_source_sink_sankey_for_all_basins",
                "export_source_sink_sankey_all_basins",
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
    )

    print("\n=== Report-card bundle complete ===")
    print(f"Output root: {result['output_root']}")
    print("Step summary:")
    print(result["step_summary"].to_string(index=False))


if __name__ == "__main__":
    main()