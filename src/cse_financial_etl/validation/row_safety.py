"""Fail-closed row-level guards discovered from full-universe production evidence.

These checks are deliberately conservative.  They do not manufacture corrected values;
they only stop structurally unsafe evidence from being published until the extractor can
resolve it unambiguously.
"""

from __future__ import annotations

import re
from decimal import Decimal

_ABSOLUTE_MONETARY = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}

_NUMBER_RE = re.compile(r"(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?\)?(?![A-Za-z])")
_NARRATIVE_AMOUNT_RE = re.compile(
    r"\b(?:lkr|rs\.?|usd|us\$)\s*\d[\d,]*(?:\.\d+)?\s*"
    r"(?:mn|millions?|bn|billions?|thousands?|['’]\s*0{3})\b",
    re.I,
)
_UNIT_DECLARATION_RE = re.compile(
    r"(?:\b(?:amounts?|figures?|values?)\b.{0,45}\b(?:in|expressed|stated|reported|presented)\b|"
    r"\b(?:expressed|stated|reported|presented)\s+in\b|"
    r"^\s*(?:lkr|rs\.?|usd|us\$)\s*(?:in\s+)?"
    r"(?:mn|millions?|bn|billions?|thousands?|['’]\s*0{3})\s*$)",
    re.I,
)


def is_positive_price(value: Decimal | None) -> bool:
    """A traded share price must be strictly positive."""

    return value is not None and value > 0


def is_narrative_unit_amount(text: str | None) -> bool:
    """Return True when text contains a transaction amount, not a unit declaration.

    Example: ``Corporate guarantee ... LKR 25 Mn`` must never become the scale for an
    unrelated financial statement merely because it appears on the same PDF page.
    """

    if not text:
        return False
    compact = " ".join(text.split())
    return bool(_NARRATIVE_AMOUNT_RE.search(compact) and not _UNIT_DECLARATION_RE.search(compact))


def suspicious_selected_numeric(
    metric_code: str,
    raw_value: Decimal | None,
    scale_factor: int | None,
    source_line: str | None,
) -> bool:
    """Detect a tiny OCR fragment selected from a row containing large monetary cells.

    This catches cases such as an OCR-corrupted equity row where ``1`` is selected while
    the same row visibly contains multi-million current/comparative values.  It is only
    applied to absolute monetary metrics in whole-unit scale, so EPS/NAVPS and note ids
    are unaffected.
    """

    if (
        metric_code not in _ABSOLUTE_MONETARY
        or raw_value is None
        or source_line is None
        or scale_factor != 1
        or abs(raw_value) > Decimal("99")
    ):
        return False
    values: list[Decimal] = []
    for match in _NUMBER_RE.finditer(source_line):
        token = match.group(0).strip("()").replace(",", "")
        try:
            values.append(abs(Decimal(token)))
        except Exception:
            continue
    threshold = max(Decimal("1000"), abs(raw_value) * Decimal("1000"))
    return any(value >= threshold for value in values)


def ratio_plausibility_issue(metric_code: str, value: Decimal) -> str | None:
    """Catch only catastrophic derived-ratio magnitudes caused by broken inputs.

    The limits are intentionally very wide; ordinary distressed/high-growth companies
    remain publishable.  Breaching them means the source facts need review rather than
    a machine-labelled PASSED derived ratio.
    """

    absolute = abs(value)
    limits = {
        "ROA": Decimal("10"),
        "ROE": Decimal("100"),
        "NPM": Decimal("1000"),
        "DEBT_TO_EQUITY": Decimal("1000"),
    }
    limit = limits.get(metric_code)
    if limit is not None and absolute > limit:
        return f"{metric_code} absolute value {value} exceeds fail-closed safety limit {limit}"
    return None
