"""Fail-closed row-level guards discovered from full-universe production evidence.

These checks are deliberately conservative. They do not manufacture corrected values;
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
_FLOW_MONETARY = {"TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"}
_STOCK_MONETARY = {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES"}
_PER_SHARE_MONETARY = {"EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED", "NAVPS"}

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
_EUROPEAN_GROUPED_RE = re.compile(r"(?<!\d)\d{1,3}(?:\.\d{3}){2,}(?!\d)")
_BROKEN_LEADING_GROUP_RE = re.compile(r"(?<![\d,]),\d{3}(?!\d)")
_ALNUM_NUMERIC_CHUNK_RE = re.compile(r"[A-Za-z0-9!,'’.]{5,}")
_DATE_HEADER_RE = re.compile(
    r"\b(?:for\s+the\s+)?(?:period|quarter|year)\s+(?:ended|ending|to)\b|"
    r"\bas\s+(?:at|of)\b",
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


def source_has_numeric_corruption(text: str | None) -> bool:
    """Detect OCR/geometry corruption inside a financial row's numeric cells.

    The failing universe exposed several deterministic corruption shapes: two cells
    concatenated into one token (``49,215,51849,465,389``), a missing leading digit
    group (``,874``), broken comma groups (``153,338156,627``), OCR letters inside a
    number (``88,81L,406``), and dotted multi-million values that the active numeric
    parser cannot consume. A row with any of these shapes is unsafe evidence; the
    correct response is to retry/review, never to publish another clean-looking token
    from the same row.
    """

    if not text:
        return False

    if _EUROPEAN_GROUPED_RE.search(text) or _BROKEN_LEADING_GROUP_RE.search(text):
        return True

    # Standard comma grouping is 1-3 leading digits followed only by groups of 3.
    for token in re.findall(r"(?<!\d)\d[\d,]*\d(?!\d)", text):
        if "," not in token:
            continue
        parts = token.split(",")
        if not (1 <= len(parts[0]) <= 3 and all(len(part) == 3 for part in parts[1:])):
            return True

    # OCR frequently substitutes letters/punctuation into a digit run. Require a
    # substantial numeric-looking chunk so normal words, dates and legal labels do not
    # trigger this guard.
    for token in _ALNUM_NUMERIC_CHUNK_RE.findall(text):
        digit_count = sum(char.isdigit() for char in token)
        if (
            digit_count >= 4
            and ("," in token or "." in token)
            and (re.search(r"[A-Za-z]", token) or "!" in token)
        ):
            return True
    return False


def per_share_source_is_unsafe(metric_code: str, source_line: str | None) -> bool:
    """Do not select a clean comparative EPS/NAVPS token from a corrupted value row.

    Per-share values are intentionally excluded from absolute-value magnitude checks,
    but column selection is still unsafe when another numeric cell on the same row is
    visibly OCR-corrupted. This is the failure shape that allowed a prior-year NAVPS to
    masquerade as CURRENT when the true current cell was damaged.
    """

    return metric_code in _PER_SHARE_MONETARY and source_has_numeric_corruption(source_line)


def _small_reference_number(raw_value: Decimal, source_line: str) -> bool:
    """Reject note/legal identifiers selected as monetary values."""

    if raw_value != raw_value.to_integral() or abs(raw_value) > 99:
        return False
    number = re.escape(str(abs(int(raw_value))))
    patterns = (
        rf"\b(?:note|section|page)\s*(?:no\.?\s*)?{number}\b",
        rf"\b(?:act|ordinance|law)\s+no\.?\s*{number}\b",
        rf"\bno\.?\s*{number}\s+of\s+(?:19|20)\d{{2}}\b",
    )
    return any(re.search(pattern, source_line, re.I) for pattern in patterns)


def _structural_context_mismatch(
    metric_code: str, raw_value: Decimal, source_line: str
) -> bool:
    """Reject headers/per-share/narrative note text masquerading as monetary rows."""

    compact = " ".join(source_line.split())
    absolute = abs(raw_value)

    # A reporting year extracted from a period/date heading is metadata, not money.
    if (
        raw_value == raw_value.to_integral()
        and Decimal("1900") <= absolute <= Decimal("2100")
        and _DATE_HEADER_RE.search(compact)
    ):
        return True

    # ``Total`` alone has no accounting concept and must never stand in for top line.
    if metric_code == "TOP_LINE" and re.fullmatch(r"total[.:]?", compact, re.I):
        return True

    # Basic/diluted labels denote per-share context, never absolute flow amounts.
    if metric_code in _FLOW_MONETARY and re.match(r"^(?:basic|diluted)\b", compact, re.I):
        return True

    # Note prose that happens to contain "income"/"revenue" must not be promoted by
    # fuzzy label matching. These are structural note cues, not issuer-specific values.
    if metric_code == "TOP_LINE":
        if re.search(r"\bfair\s+value\b.{0,100}\b(?:level|land|property)\b", compact, re.I):
            return True
        if re.search(
            r"\bcorresponding\s+quarter\b.{0,120}\b(?:previous\s+year|composition\s+of)\b",
            compact,
            re.I,
        ):
            return True

    return False


def suspicious_selected_numeric(
    metric_code: str,
    raw_value: Decimal | None,
    scale_factor: int | None,
    source_line: str | None,
) -> bool:
    """Detect an unsafe numeric selection from an absolute-monetary source row.

    This covers corrupted numeric cells, structural headers/note prose, tiny reference
    numbers, and tiny fragments selected from visibly large rows. EPS/NAVPS use the
    separate per-share corruption guard because their magnitudes are naturally small.
    """

    if metric_code not in _ABSOLUTE_MONETARY or raw_value is None or source_line is None:
        return False

    if source_has_numeric_corruption(source_line):
        return True

    if _small_reference_number(raw_value, source_line):
        return True

    if _structural_context_mismatch(metric_code, raw_value, source_line):
        return True

    if scale_factor != 1 or abs(raw_value) > Decimal("99"):
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


def inconsistent_scale_metrics(
    values: dict[str, tuple[Decimal | None, int | None]],
) -> set[str]:
    """Return absolute metrics that cannot safely retain their inferred scale.

    We never rescale a value here. Within one statement family, core absolute metrics
    must not silently alternate between whole units and thousands/millions. Across the
    profit/loss and balance-sheet statements, different printed scales are allowed, but
    a 1000x+ scale split becomes blocking when it also creates an economically
    catastrophic relationship (quarter PAT > assets/equity, or quarterly top line >
    10x assets). In that cross-statement case the implicit lower/whole-unit side is
    withheld while the explicit scaled side is retained for reviewable provenance.
    """

    usable = {
        code: (value, scale)
        for code, (value, scale) in values.items()
        if code in _ABSOLUTE_MONETARY
        and value is not None
        and scale is not None
        and scale > 0
    }
    unsafe: set[str] = set()

    def family_conflicts(codes: set[str]) -> None:
        members = [(code, usable[code]) for code in codes if code in usable]
        scales = [scale for _code, (_value, scale) in members]
        if len(scales) < 2:
            return
        low = min(scales)
        high = max(scales)
        if high >= low * 1000:
            # Same P&L / balance-sheet family but incompatible scale ownership. We
            # cannot know which side is right, so all conflicting family values wait
            # for stronger unit evidence.
            unsafe.update(code for code, _pair in members)

    family_conflicts(_FLOW_MONETARY)
    family_conflicts(_STOCK_MONETARY)

    def cross_contradiction(
        numerator_code: str,
        denominator_code: str,
        *,
        threshold: Decimal,
    ) -> None:
        if numerator_code in unsafe or denominator_code in unsafe:
            return
        numerator = usable.get(numerator_code)
        denominator = usable.get(denominator_code)
        if numerator is None or denominator is None:
            return
        numerator_value, numerator_scale = numerator
        denominator_value, denominator_scale = denominator
        assert numerator_value is not None and denominator_value is not None
        assert numerator_scale is not None and denominator_scale is not None
        if denominator_value <= 0:
            return
        low_scale = min(numerator_scale, denominator_scale)
        high_scale = max(numerator_scale, denominator_scale)
        if high_scale < low_scale * 1000:
            return
        if abs(numerator_value / denominator_value) <= threshold:
            return
        # A scale of 1000/1e6 has explicit magnitude evidence. A scale of 1 is often
        # only a bare-currency fallback; with a catastrophic cross-statement
        # contradiction, that implicit side is no longer safe to publish.
        if low_scale == 1:
            unsafe.update(
                code
                for code, (_value, scale) in usable.items()
                if scale == low_scale
            )
        else:
            unsafe.update({numerator_code, denominator_code})

    cross_contradiction("PAT", "TOTAL_ASSETS", threshold=Decimal("1"))
    cross_contradiction("PAT", "TOTAL_EQUITY", threshold=Decimal("1"))
    cross_contradiction("TOP_LINE", "TOTAL_ASSETS", threshold=Decimal("10"))
    return unsafe


def ratio_plausibility_issue(metric_code: str, value: Decimal) -> str | None:
    """Catch only catastrophic derived-ratio magnitudes caused by broken inputs.

    The limits are intentionally very wide; ordinary distressed/high-growth companies
    remain publishable. Breaching them means the source facts need review rather than
    a machine-labelled PASSED derived ratio.
    """

    absolute = abs(value)
    limits = {
        "ROA": Decimal("10"),
        "ROE": Decimal("100"),
        "NPM": Decimal("100"),
        "DEBT_TO_EQUITY": Decimal("1000"),
    }
    limit = limits.get(metric_code)
    if limit is not None and absolute > limit:
        return f"{metric_code} absolute value {value} exceeds fail-closed safety limit {limit}"
    return None
