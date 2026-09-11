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
    """Detect adjacent statement continuations from positive source evidence only.

    Classifier uncertainty is deliberately not treated as continuation evidence.
    Regions spanning multiple pages are expanded back to page membership so this
    detector remains useful after conservative region merging.
    """

    links: list[ContinuationLink] = []
    by_page: dict[int, StatementRegion] = {}
    for region in regions:
        for page_number in range(region.page_start, region.page_end + 1):
            by_page[page_number] = region
    pages = {page.page_number: page for page in document.pages}
    for page_no in sorted(pages):
        nxt = page_no + 1
        if nxt not in pages or page_no not in by_page or nxt not in by_page:
            continue
        previous = by_page[page_no]
        current = by_page[nxt]
        if previous.statement_type != current.statement_type or previous.statement_type == "OTHER":
            continue
        evidenced = _has_repeated_header(pages[nxt])
        links.append(
            ContinuationLink(
                from_page=page_no,
                to_page=nxt,
                statement_type=previous.statement_type,
                evidenced=evidenced,
                reason="repeated_source_header" if evidenced else "adjacent_same_type_unconfirmed",
            )
        )
    return links


def _has_repeated_header(page: PageIR) -> bool:
    blob = " ".join(line.text.lower() for line in page.lines[:8])
    entity = any(cue in blob for cue in ("company", "group", "bank"))
    unit = any(cue in blob for cue in ("rs", "lkr", "rupees"))
    temporal = any(
        cue in blob
        for cue in (
            "three months",
            "six months",
            "nine months",
            "twelve months",
            "period ended",
            "quarter ended",
            "year ended",
            "as at",
        )
    )
    return temporal and (entity or unit)
