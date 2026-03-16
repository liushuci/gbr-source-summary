from gbr_source_summary.report_card_summary import run_report_card_summary


def test_run_report_card_summary_import():
    assert callable(run_report_card_summary)