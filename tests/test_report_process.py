from gbr_source_summary.report_process import (
    run_process_report,
    run_all_gbr_process_reports,
)


def test_run_process_report_import():
    assert callable(run_process_report)


def test_run_all_gbr_process_reports_import():
    assert callable(run_all_gbr_process_reports)