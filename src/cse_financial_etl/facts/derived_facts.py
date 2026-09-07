"""Derived ratios from approved source facts only (§4). Never blank→0."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class DerivedRatio:
    code: str
    value: Decimal | None
    status: str
    issue: str | None


def compute_quarter_ratios(
    *,
    pat: Decimal | None,
    equity: Decimal | None,
    assets: Decimal | None,
    liabilities: Decimal | None,
    top_line: Decimal | None,
) -> list[DerivedRatio]:
    return [
        _ratio("DEBT_TO_EQUITY", liabilities, equity, "Total Liabilities / Total Equity"),
        _ratio("ROE_Q", pat, equity, "quarter PAT / quarter-end Total Equity"),
        _ratio("ROA_Q", pat, assets, "quarter PAT / quarter-end Total Assets"),
        _ratio("NPM_Q", pat, top_line, "quarter PAT / quarter top line"),
    ]


def _ratio(
    code: str,
    numerator: Decimal | None,
    denominator: Decimal | None,
    formula: str,
) -> DerivedRatio:
    if numerator is None or denominator is None:
        missing = []
        if numerator is None:
            missing.append("numerator")
        if denominator is None:
            missing.append("denominator")
        return DerivedRatio(
            code,
            None,
            "INSUFFICIENT_INPUT",
            f"{code} blocked: missing {', '.join(missing)} ({formula})",
        )
    if denominator == 0:
        return DerivedRatio(code, None, "ZERO_EQUITY" if "Equity" in formula else "NON_POSITIVE_DENOMINATOR", formula)
    if denominator < 0:
        return DerivedRatio(code, None, "NON_POSITIVE_DENOMINATOR", f"negative denominator under policy ({formula})")
    return DerivedRatio(code, numerator / denominator, "EXTRACTED_DERIVED", formula)
