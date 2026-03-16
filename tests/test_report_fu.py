from gbr_source_summary.report_fu import run_all_gbr_fu_reports, run_fu_report


def test_run_fu_report_import():
    assert callable(run_fu_report)


def test_run_all_gbr_fu_reports_import():
    assert callable(run_all_gbr_fu_reports)