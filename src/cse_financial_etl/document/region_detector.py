"""Detect statement / region types from headings and source-owned continuation evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from cse_financial_etl.document.document_ir import CanonicalDocumentIR, PageIR

_HEADING_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PROFIT_LOSS", re.compile(r"statement of (?:profit|income)|income statement|profit or loss", re.I)),
    ("COMPREHENSIVE_INCOME", re.compile(r"comprehensive income", re.I)),
    ("FINANCIAL_POSITION", re.compile(r"financial position|balance sheet|statement of financial", re.I)),
    ("CASH_FLOW", re.compile(r"cash flows?", re.I)),
    ("CHANGES_IN_EQUITY", re.compile(r"changes in equity|statement of changes", re.I)),
    ("NOTES", re.compile(r"^notes? to the|explanatory notes", re.I)),
    ("SHARE_INFORMATION", re.compile(r"share information|earnings per share|net asset.*per share", re.I)),
    ("SEGMENT_INFORMATION", re.compile(r"segment (?:information|reporting)", re.I)),
    ("RELATED_PARTY", re.compile(r"related part(?:y|ies)", re.I)),
    ("FINANCIAL_HIGHLIGHTS", re.compile(r"financial highlights|key performance", re.I)),
)

_AUTHORITATIVE_REGION_CONFIDENCE = 0.8
_CONTINUATION_ENTITY_RE = re.compile(r"\b(?:group|company|bank)\b", re.I)
_CONTINUATION_UNIT_RE = re.compile(r"\b(?:lkr|rs\.?|rupees?)\b", re.I)
_CONTINUATION_PERIOD_RE = re.compile(
    r"\b(?:three|six|nine|twelve)\s+months?\b|period ended|year ended|quarter ended|as at",
    re.I,
)
_CONTINUATION_DATE_RE = re.compile(
    r"\b(?:31|30|29|28)\s+(?:mar(?:ch)?|jun(?:e)?|sep(?:tember)?|dec(?:ember)?)\s+20\d{2}\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class StatementRegion:
    statement_type: str
    page_start: int
    page_end: int
    evidence: str
    confidence: float


def detect_regions(document: CanonicalDocumentIR) -> list[StatementRegion]:
    """Classify pages, promote only source-evidenced continuations, then merge safely.

    Numeric-density classification is intentionally weak.  A weak page may inherit
    a statement type only when its own repeated entity/unit/period header agrees
    with an authoritative adjacent page.  Merger confidence is conservative so a
    weak page can never become authoritative merely by sitting beside a strong one.
    """

    raw_regions = [_classify_page(page) for page in document.pages]
    promoted = _promote_evidenced_continuations(document, raw_regions)
    return _merge_contiguous(promoted)


def _classify_page(page: PageIR) -> StatementRegion:
    heading = _page_heading(page)
    matched = "OTHER"
    confidence = 0.2
    first = page.lines[0].text if page.lines else ""
    for statement_type, pattern in _HEADING_RULES:
        if pattern.search(heading) or pattern.search(first):
            matched = statement_type
            confidence = 0.9
            break
    if matched == "OTHER" and _numeric_density(page) > 0.35:
        matched = "FINANCIAL_POSITION" if _looks_like_sofp(page) else "PROFIT_LOSS"
        confidence = 0.45
    return StatementRegion(
        statement_type=matched,
        page_start=page.page_number,
        page_end=page.page_number,
        evidence=heading[:240],
        confidence=confidence,
    )


def _promote_evidenced_continuations(
    document: CanonicalDocumentIR,
    regions: list[StatementRegion],
) -> list[StatementRegion]:
    if len(regions) < 2:
        return regions
    pages = {page.page_number: page for page in document.pages}
    promoted = list(regions)
    for idx in range(1, len(promoted)):
        previous = promoted[idx - 1]
        current = promoted[idx]
        if current.page_start != previous.page_end + 1:
            continue
        if previous.confidence < _AUTHORITATIVE_REGION_CONFIDENCE:
            continue
        if current.confidence >= _AUTHORITATIVE_REGION_CONFIDENCE:
            continue
        if current.statement_type == "OTHER" or current.statement_type != previous.statement_type:
            continue
        previous_page = pages.get(previous.page_end)
        current_page = pages.get(current.page_start)
        if previous_page is None or current_page is None:
            continue
        continuation_evidence = _continuation_evidence(previous_page, current_page)
        if continuation_evidence is None:
            continue
        promoted[idx] = StatementRegion(
            statement_type=current.statement_type,
            page_start=current.page_start,
            page_end=current.page_end,
            evidence=f"{current.evidence} | continuation:{continuation_evidence}"[:500],
            confidence=_AUTHORITATIVE_REGION_CONFIDENCE,
        )
    return promoted


def _continuation_evidence(previous: PageIR, current: PageIR) -> str | None:
    """Return positive source evidence for a cross-page statement continuation.

    Low classifier confidence is never evidence.  We require a repeated financial
    table header signature shared by both pages, including a date/period cue plus
    at least one entity or unit cue, and the candidate page must remain numeric.
    """

    if _numeric_density(current) <= 0.25:
        return None
    previous_cues = _header_cues(previous)
    current_cues = _header_cues(current)
    shared = previous_cues & current_cues
    temporal = bool({"DATE", "PERIOD"} & shared)
    scope = bool({"ENTITY", "UNIT"} & shared)
    if not (temporal and scope):
        return None
    return "+".join(sorted(shared))


def _header_cues(page: PageIR) -> set[str]:
    blob = " ".join(line.text for line in page.lines[:10])
    cues: set[str] = set()
    if _CONTINUATION_ENTITY_RE.search(blob):
        cues.add("ENTITY")
    if _CONTINUATION_UNIT_RE.search(blob):
        cues.add("UNIT")
    if _CONTINUATION_PERIOD_RE.search(blob):
        cues.add("PERIOD")
    if _CONTINUATION_DATE_RE.search(blob):
        cues.add("DATE")
    return cues


def _page_heading(page: PageIR) -> str:
    return " | ".join(line.text for line in page.lines[:8])


def _numeric_density(page: PageIR) -> float:
    if not page.tokens:
        return 0.0
    numeric = sum(1 for token in page.tokens if any(ch.isdigit() for ch in token.text))
    return numeric / max(1, len(page.tokens))


def _looks_like_sofp(page: PageIR) -> bool:
    blob = " ".join(line.text for line in page.lines[:20]).lower()
    return any(key in blob for key in ("total assets", "equity", "liabilities", "non-current"))


def _merge_contiguous(regions: list[StatementRegion]) -> list[StatementRegion]:
    if not regions:
        return []
    merged: list[StatementRegion] = [regions[0]]
    for region in regions[1:]:
        previous = merged[-1]
        both_authoritative = (
            previous.confidence >= _AUTHORITATIVE_REGION_CONFIDENCE
            and region.confidence >= _AUTHORITATIVE_REGION_CONFIDENCE
        )
        if (
            both_authoritative
            and region.statement_type == previous.statement_type
            and region.page_start == previous.page_end + 1
        ):
            merged[-1] = StatementRegion(
                statement_type=previous.statement_type,
                page_start=previous.page_start,
                page_end=region.page_end,
                evidence=f"{previous.evidence} || p{region.page_start}:{region.evidence}"[:500],
                confidence=min(previous.confidence, region.confidence),
            )
        else:
            merged.append(region)
    return merged
