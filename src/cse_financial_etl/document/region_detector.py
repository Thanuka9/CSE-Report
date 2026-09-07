"""Detect statement / region types from headings and numeric density (Revision 2 §9)."""

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


@dataclass(frozen=True, slots=True)
class StatementRegion:
    statement_type: str
    page_start: int
    page_end: int
    evidence: str
    confidence: float


def detect_regions(document: CanonicalDocumentIR) -> list[StatementRegion]:
    regions: list[StatementRegion] = []
    for page in document.pages:
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
        regions.append(
            StatementRegion(
                statement_type=matched,
                page_start=page.page_number,
                page_end=page.page_number,
                evidence=heading[:240],
                confidence=confidence,
            )
        )
    return _merge_contiguous(regions)


def _page_heading(page: PageIR) -> str:
    return " | ".join(line.text for line in page.lines[:8])


def _numeric_density(page: PageIR) -> float:
    if not page.tokens:
        return 0.0
    numeric = sum(1 for t in page.tokens if any(ch.isdigit() for ch in t.text))
    return numeric / max(1, len(page.tokens))


def _looks_like_sofp(page: PageIR) -> bool:
    blob = " ".join(line.text for line in page.lines[:20]).lower()
    return any(key in blob for key in ("total assets", "equity", "liabilities", "non-current"))


def _merge_contiguous(regions: list[StatementRegion]) -> list[StatementRegion]:
    if not regions:
        return []
    merged: list[StatementRegion] = [regions[0]]
    for region in regions[1:]:
        prev = merged[-1]
        if region.statement_type == prev.statement_type and region.page_start == prev.page_end + 1:
            merged[-1] = StatementRegion(
                statement_type=prev.statement_type,
                page_start=prev.page_start,
                page_end=region.page_end,
                evidence=prev.evidence,
                confidence=max(prev.confidence, region.confidence),
            )
        else:
            merged.append(region)
    return merged
