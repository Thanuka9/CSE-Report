"""Last traded as-of quarter end. Closing/snapshot substitutions stay forbidden."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.sources.historical_prices import resolve_quarter_end_price


def resolve_last_traded_as_of_quarter_end(
    project_root: Path,
    symbol: str,
    period_end: date,
) -> tuple[Decimal, date, str] | None:
    """Exact security, last valid trade on or before quarter end.

    Delegates to the governed V1 historical resolver so production prices stay
    last-traded-only. A trade date after ``period_end`` is never returned by
    that resolver.
    """

    resolved = resolve_quarter_end_price(project_root, symbol, period_end)
    if resolved is None:
        return None
    value, observed, method = resolved
    if observed > period_end:
        return None
    return value, observed, method
