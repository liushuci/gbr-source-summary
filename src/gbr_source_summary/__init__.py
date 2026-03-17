"""
gbr_source_summary package.

This package provides reusable tools for summarising GBR Source model outputs,
including:
- configuration and path handling
- file loading for Source output tables
- naming standardisation for constituents and management units
- model evaluation metrics
- FU-based summary builders

The __init__.py file exposes the main public API for convenient imports.
"""

from .comparison import (
    calc_anthropogenic,
    calc_percent_reduction,
    calc_reduction,
)
from .config import GBRConfig
from .export import (
    ensure_output_dir,
    export_constituent_tables_csv,
    export_region_tables_csv,
    export_report_tables,
    export_table_csv,
)
from .export_excel import export_tables_to_excel
from .io import (
    load_reg_contributor_data_grid_with_lut,
    load_region_lut,
    load_source_outputs,
)
from .metrics import calc_nse, calc_pbias, calc_r2, calc_rsr
from .naming import (
    apply_constituent_name_standardisation,
    apply_management_unit_standardisation,
    standardise_constituent_names,
    standardise_management_unit_names,
)
from .qa_checks import (
    check_anthropogenic_consistency,
    check_no_negative_values,
    check_percent_reduction_bounds,
    check_reduction_consistency,
    check_sum_matches_total,
)
from .regions import resolve_regions
from .report_fu import run_all_gbr_fu_reports, run_fu_report
from .report_process import run_all_gbr_process_reports, run_process_report
from .summary_flow import (
    aggregate_flow_tables,
    build_basin_flow_summary,
    build_fu_flow_summary,
    build_group_flow_summary,
)
from .summary_fu import (
    aggregate_gbr_fu_summary,
    aggregate_region_fu_summary,
    build_basin_fu_summary,
)
from .summary_process import (
    aggregate_gbr_process_summary,
    aggregate_region_process_summary,
    build_basin_process_summary,
)
from .workflows_compare import (
    build_fu_basin_scenario_comparison,
    build_fu_scenario_comparison,
    flatten_basin_tables,
)
from .workflows_flow import (
    build_flow_summaries,
    build_region_flow_summary,
)
from .workflows_fu import (
    build_fu_export_summaries,
    build_region_fu_export_summary,
)
from .workflows_process import (
    build_process_export_summaries,
    build_region_process_export_summary,
)
from .report_card_summary import run_report_card_summary


from .workflows_basin import (
    build_basin_export_summaries,
    build_basin_scenario_comparison,
)


from .load_basin_lookup import load_basin_lookup


__all__ = [
    "GBRConfig",
    "resolve_regions",
    "load_source_outputs",
    "load_region_lut",
    "load_reg_contributor_data_grid_with_lut",
    "calc_nse",
    "calc_pbias",
    "calc_r2",
    "calc_rsr",
    "apply_constituent_name_standardisation",
    "apply_management_unit_standardisation",
    "standardise_constituent_names",
    "standardise_management_unit_names",
    "build_basin_fu_summary",
    "aggregate_region_fu_summary",
    "aggregate_gbr_fu_summary",
    "build_basin_process_summary",
    "aggregate_region_process_summary",
    "aggregate_gbr_process_summary",
    "build_group_flow_summary",
    "build_fu_flow_summary",
    "build_basin_flow_summary",
    "aggregate_flow_tables",
    "build_region_flow_summary",
    "build_flow_summaries",
    "build_region_fu_export_summary",
    "build_fu_export_summaries",
    "build_region_process_export_summary",
    "build_process_export_summaries",
    "build_fu_scenario_comparison",
    "build_fu_basin_scenario_comparison",
    "flatten_basin_tables",
    "calc_anthropogenic",
    "calc_reduction",
    "calc_percent_reduction",
    "ensure_output_dir",
    "export_table_csv",
    "export_region_tables_csv",
    "export_constituent_tables_csv",
    "export_report_tables",
    "export_tables_to_excel",
    "check_no_negative_values",
    "check_sum_matches_total",
    "check_anthropogenic_consistency",
    "check_reduction_consistency",
    "check_percent_reduction_bounds",
    "run_fu_report",
    "run_all_gbr_fu_reports",
    "run_process_report",
    "run_all_gbr_process_reports",
    "run_report_card_summary",

    
    "build_basin_export_summaries",
    "build_basin_scenario_comparison",
    "load_basin_lookup",
]