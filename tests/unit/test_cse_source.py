from datetime import date

from cse_financial_etl.sources.cse import parse_period_end


def test_parse_period_end_handles_cse_titles() -> None:
    assert parse_period_end(
        "Interim Financial Statements for the Quarter ended 30th June 2026"
    ) == date(2026, 6, 30)
    assert parse_period_end("Interim Financial Statements as @ 31st December 2025") == date(
        2025, 12, 31
    )


def test_parse_period_end_rejects_unrelated_title() -> None:
    assert parse_period_end("Annual report") is None
