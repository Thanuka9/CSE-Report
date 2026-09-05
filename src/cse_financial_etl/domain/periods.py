from __future__ import annotations

from collections.abc import Iterable
from datetime import date


def shift_quarter(period_end: date, quarters_back: int) -> date:
    total_months = period_end.year * 12 + period_end.month - 1 - quarters_back * 3
    year, month_index = divmod(total_months, 12)
    month = month_index + 1
    day = 31 if month in {3, 12} else 30
    return date(year, month, day)


def supporting_periods(display_periods: Iterable[date]) -> tuple[date, ...]:
    """Return only requested quarter ends; no TTM or cumulative-delta history is needed."""

    return tuple(sorted(set(display_periods)))
