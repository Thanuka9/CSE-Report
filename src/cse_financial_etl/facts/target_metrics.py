"""14-field publish contract target queries (§4, §36)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

TARGET_METRIC_CODES: tuple[str, ...] = (
    "PAT",
    "PBT",
    "EPS_SELECTED",  # diluted when valid/reported, otherwise basic
    "NAVPS",
    "OPERATING_PROFIT",
    "TOTAL_EQUITY",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOP_LINE",
    "MARKET_PRICE_QUARTER_END",
    "DEBT_TO_EQUITY",  # legacy internal code; canonical semantic is LIABILITIES_TO_EQUITY
    "ROE",
    "ROA",
    "NPM",
)


@dataclass(frozen=True, slots=True)
class TargetQuery:
    metric_code: str
    statement_type: str | None
    concept: str
    entity: str
    duration_months: int | None
    comparison_role: str
    period_end: date


def default_queries(*, entity: str, period_end: date) -> list[TargetQuery]:
    specs = [
        ("PAT", "PROFIT_LOSS", "PAT", 3),
        ("PBT", "PROFIT_LOSS", "PBT", 3),
        ("EPS_BASIC", "PROFIT_LOSS", "EPS_BASIC", 3),
        ("EPS_DILUTED", "PROFIT_LOSS", "EPS_DILUTED", 3),
        ("NAVPS", "FINANCIAL_POSITION", "NAVPS", None),
        ("OPERATING_PROFIT", "PROFIT_LOSS", "OPERATING_PROFIT", 3),
        ("TOTAL_EQUITY", "FINANCIAL_POSITION", "TOTAL_EQUITY", None),
        ("TOTAL_ASSETS", "FINANCIAL_POSITION", "TOTAL_ASSETS", None),
        ("TOTAL_LIABILITIES", "FINANCIAL_POSITION", "TOTAL_LIABILITIES", None),
        ("TOP_LINE", "PROFIT_LOSS", "TOP_LINE", 3),
    ]
    return [
        TargetQuery(
            metric_code=code,
            statement_type=stmt,
            concept=concept,
            entity=entity,
            duration_months=duration,
            comparison_role="CURRENT",
            period_end=period_end,
        )
        for code, stmt, concept, duration in specs
    ]
