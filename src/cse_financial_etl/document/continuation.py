"""Cross-page table continuation detection and evidenced header inheritance."""

from __future__ import annotations

from dataclasses import dataclass

from cse_financial_etl.document.document_ir import CanonicalDocumentIR, PageIR
from cse_financial_etl.document.region_detector import StatementRegion


@dataclass(frozen=True, slots=True)
class ContinuationLink:
    from_page: int
    to_page: int
    statement_type: str
    evidenced: bool
    reason: str


def detect_continuations(
    document: CanonicalDocumentIR,
    regions: list[StatementRegion],
) -> list[ContinuationLink]:
    links: list[ContinuationLink] = []
    by_page = {r.page_start: r for r in regions}
    pages = {p.page_number: p for p in document.pages}
    for page_no in sorted(pages):
        nxt = page_no + 1
        if nxt not in pages or page_no not in by_page or nxt not in by_page:
            continue
        a = by_page[page_no]
        b = by_page[nxt]
        if a.statement_type != b.statement_type or a.statement_type == "OTHER":
            continue
        evidenced = _has_repeated_header(pages[nxt]) or b.confidence < 0.5
        links.append(
            ContinuationLink(
                from_page=page_no,
                to_page=nxt,
                statement_type=a.statement_type,
                evidenced=evidenced,
                reason="same_statement_type_adjacent"
                if evidenced
                else "adjacent_same_type_unconfirmed",
            )
        )
    return links


def _has_repeated_header(page: PageIR) -> bool:
    blob = " ".join(line.text.lower() for line in page.lines[:5])
    cues = ("company", "group", "rs", "three months", "period ended", "as at")
    return sum(1 for cue in cues if cue in blob) >= 2
