from datetime import date

from cse_financial_etl.cli import _rolling_periods


def test_rolling_periods_uses_latest_three_completed_quarters() -> None:
    assert _rolling_periods(date(2026, 9, 4)) == (
        date(2025, 12, 31),
        date(2026, 3, 31),
        date(2026, 6, 30),
    )
