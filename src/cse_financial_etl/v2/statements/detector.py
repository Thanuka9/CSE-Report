"""Deterministic statement-page/region detection from CanonicalDocument headings.

Classification uses explicit heading evidence in the page heading band only.
Numeric density never invents a statement type. Notes, contents pages, and
cross-references in note bodies are constrained to OTHER_FINANCIAL_STATEMENT.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cse_financial_etl.v2 import PARSER_NAME_NATIVE, PARSER_VERSION_NATIVE, SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalLine, CanonicalPage
from cse_financial_etl.v2.contracts.enums import StatementType
from cse_financial_etl.v2.contracts.provenance import SourceRef

HEADING_BAND_LINES = 12

# Most-specific titles first so an EPS note is not swallowed by a generic income phrase.
_TITLE_RULES: tuple[tuple[StatementType, re.Pattern[str]], ...] = (
    (
        StatementType.EPS_NOTE,
        re.compile(
            r"earnings per share|diluted earnings|basic earnings|"
            r"net assets? per share|net asset value per share|investor information",
            re.IGNORECASE,
        ),
    ),
    (
        StatementType.CHANGES_IN_EQUITY,
        re.compile(
            r"changes in (?:equity|shareholders['’]? funds)|statement of changes",
            re.IGNORECASE,
        ),
    ),
    (
        StatementType.CASH_FLOW,
        re.compile(r"cash flows?|statement of cash", re.IGNORECASE),
    ),
    (
        StatementType.BALANCE_SHEET,
        re.compile(
            r"financial position|balance sheet|statement of financial",
            re.IGNORECASE,
        ),
    ),
    (
        StatementType.INCOME_STATEMENT,
        re.compile(
            r"statement of (?:profit|income)|income statement|profit or loss|"
            r"comprehensive income|statement of comprehensive",
            re.IGNORECASE,
        ),
    ),
)

_NOTES_HEADING = re.compile(
    r"notes? to (?:the )?(?:interim |condensed )?(?:consolidated )?financial statements"
    r"|explanatory notes"
    r"|significant accounting policies"
    r"|accounting policies",
    re.IGNORECASE,
)
_TOC_LINE = re.compile(
    r"^(?:table of )?contents$|^index(?: of (?:statements|contents))?$",
    re.IGNORECASE,
)
_CONTINUED = re.compile(
    r"\b(?:continued|continuation|cont(?:inued)?\.?|cont['’]?d)\b",
    re.IGNORECASE,
)


class StatementRegion(BaseModel):
    """A detected statement region. Rows/columns are Phase 5 reconstruction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    region_id: str
    statement_type: StatementType
    page_start: int
    page_end: int
    heading_text: str
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    reason_codes: tuple[str, ...] = ()


def detect_statement_regions(document: CanonicalDocument) -> tuple[StatementRegion, ...]:
    """Return merged statement regions with source-bound heading evidence."""

    per_page = [_classify_page(document, page) for page in document.pages]
    continued = _apply_explicit_continuations(document, per_page)
    return _merge_contiguous(continued)


def _heading_band(page: CanonicalPage) -> tuple[CanonicalLine, ...]:
    return page.lines[:HEADING_BAND_LINES]


def _parser_identity(document: CanonicalDocument) -> tuple[str, str]:
    name = document.parser_manifest.get("parser_name") or PARSER_NAME_NATIVE
    version = document.parser_manifest.get("parser_version") or PARSER_VERSION_NATIVE
    return name, version


def _source_ref(
    document: CanonicalDocument,
    line: CanonicalLine,
    *,
    page_number: int,
) -> SourceRef:
    parser_name, parser_version = _parser_identity(document)
    return SourceRef(
        filing_id=document.filing_version_id,
        filing_version_id=document.filing_version_id,
        source_sha256=document.source_sha256,
        page_number=page_number,
        bbox=line.bbox,
        raw_text=line.text,
        parser_name=parser_name,
        parser_version=parser_version,
    )


_HEADING_START = re.compile(
    r"^(?:(?:consolidated|company|group|bank|condensed|interim|statements? of)\b|"
    r"income statement|financial position|balance sheet|earnings per|changes in|"
    r"net assets? per share|net asset value per share|investor information)",
    re.IGNORECASE,
)


def _looks_like_title_line(text: str) -> bool:
    """Ignore narrative sentences that merely mention a statement name."""

    stripped = " ".join(text.split())
    if not stripped or len(stripped) > 96:
        return False
    if stripped.count(" ") > 14:
        return False
    return _HEADING_START.search(stripped) is not None


def _match_type(text: str) -> StatementType | None:
    for statement_type, pattern in _TITLE_RULES:
        if pattern.search(text):
            return statement_type
    return None


def _is_toc_page(lines: tuple[CanonicalLine, ...]) -> bool:
    return any(_TOC_LINE.match(line.text.strip()) for line in lines[:4])


def _classify_page(document: CanonicalDocument, page: CanonicalPage) -> StatementRegion:
    band = _heading_band(page)
    heading_text = " | ".join(line.text for line in band)
    parser_name, parser_version = _parser_identity(document)
    page_ref = SourceRef(
        filing_id=document.filing_version_id,
        filing_version_id=document.filing_version_id,
        source_sha256=document.source_sha256,
        page_number=page.page_number,
        bbox=(0.0, 0.0, page.width, page.height),
        raw_text=heading_text or None,
        parser_name=parser_name,
        parser_version=parser_version,
    )
    if not band:
        return StatementRegion(
            region_id=f"p{page.page_number:04d}-OTHER_FINANCIAL_STATEMENT",
            statement_type=StatementType.OTHER_FINANCIAL_STATEMENT,
            page_start=page.page_number,
            page_end=page.page_number,
            heading_text="",
            source_refs=(page_ref,),
            reason_codes=("EMPTY_PAGE",),
        )

    fallback_line = band[0]

    if _is_toc_page(band):
        return StatementRegion(
            region_id=f"p{page.page_number:04d}-OTHER_FINANCIAL_STATEMENT",
            statement_type=StatementType.OTHER_FINANCIAL_STATEMENT,
            page_start=page.page_number,
            page_end=page.page_number,
            heading_text=heading_text,
            source_refs=(_source_ref(document, fallback_line, page_number=page.page_number),),
            reason_codes=("CONTENTS_PAGE",),
        )

    notes_hits = [line for line in band if _NOTES_HEADING.search(line.text)]
    title_hits: list[tuple[StatementType, CanonicalLine]] = []
    for line in band:
        if not _looks_like_title_line(line.text):
            continue
        matched = _match_type(line.text)
        if matched is not None:
            title_hits.append((matched, line))

    distinct_types = {item[0] for item in title_hits}
    if notes_hits and (
        not title_hits
        or min(band.index(line) for line in notes_hits)
        <= min(band.index(hit[1]) for hit in title_hits)
    ):
        return StatementRegion(
            region_id=f"p{page.page_number:04d}-OTHER_FINANCIAL_STATEMENT",
            statement_type=StatementType.OTHER_FINANCIAL_STATEMENT,
            page_start=page.page_number,
            page_end=page.page_number,
            heading_text=heading_text,
            source_refs=(_source_ref(document, notes_hits[0], page_number=page.page_number),),
            reason_codes=("NOTES_REGION",),
        )

    if len(distinct_types) > 1:
        return StatementRegion(
            region_id=f"p{page.page_number:04d}-OTHER_FINANCIAL_STATEMENT",
            statement_type=StatementType.OTHER_FINANCIAL_STATEMENT,
            page_start=page.page_number,
            page_end=page.page_number,
            heading_text=heading_text,
            source_refs=tuple(
                _source_ref(document, line, page_number=page.page_number)
                for _, line in title_hits[:4]
            ),
            reason_codes=("MULTI_STATEMENT_INDEX",),
        )

    if title_hits:
        statement_type, evidence_line = title_hits[0]
        return StatementRegion(
            region_id=f"p{page.page_number:04d}-{statement_type.value}",
            statement_type=statement_type,
            page_start=page.page_number,
            page_end=page.page_number,
            heading_text=heading_text,
            source_refs=(_source_ref(document, evidence_line, page_number=page.page_number),),
            reason_codes=("HEADING_MATCH",),
        )

    return StatementRegion(
        region_id=f"p{page.page_number:04d}-OTHER_FINANCIAL_STATEMENT",
        statement_type=StatementType.OTHER_FINANCIAL_STATEMENT,
        page_start=page.page_number,
        page_end=page.page_number,
        heading_text=heading_text,
        source_refs=(_source_ref(document, fallback_line, page_number=page.page_number),),
        reason_codes=("NO_STATEMENT_HEADING",),
    )


def _page_has_continuation_marker(page: CanonicalPage) -> bool:
    band = _heading_band(page)
    footer = page.lines[-3:] if page.lines else ()
    return any(_CONTINUED.search(line.text) for line in (*band, *footer))


def _conflicting_entity_heading(text: str) -> bool:
    has_group = re.search(r"\b(?:group|consolidated)\b", text, re.I) is not None
    has_company = re.search(r"\b(?:company|separate)\b", text, re.I) is not None
    has_bank = re.search(r"\bbank\b", text, re.I) is not None
    return sum(bool(flag) for flag in (has_group, has_company, has_bank)) >= 2


def _apply_explicit_continuations(
    document: CanonicalDocument,
    regions: list[StatementRegion],
) -> list[StatementRegion]:
    if not regions:
        return regions
    pages = {page.page_number: page for page in document.pages}
    promoted = list(regions)
    for index in range(1, len(promoted)):
        previous = promoted[index - 1]
        current = promoted[index]
        if current.page_start != previous.page_end + 1:
            continue
        if previous.statement_type == StatementType.OTHER_FINANCIAL_STATEMENT:
            continue
        if current.statement_type not in {
            StatementType.OTHER_FINANCIAL_STATEMENT,
            previous.statement_type,
        }:
            continue
        page = pages.get(current.page_start)
        if page is None or not _page_has_continuation_marker(page):
            continue
        if _conflicting_entity_heading(current.heading_text):
            continue
        promoted[index] = StatementRegion(
            region_id=f"p{current.page_start:04d}-{previous.statement_type.value}",
            statement_type=previous.statement_type,
            page_start=current.page_start,
            page_end=current.page_end,
            heading_text=current.heading_text,
            source_refs=current.source_refs,
            reason_codes=(*current.reason_codes, "EXPLICIT_CONTINUATION"),
        )
    return promoted


def _merge_contiguous(regions: list[StatementRegion]) -> tuple[StatementRegion, ...]:
    if not regions:
        return ()
    merged: list[StatementRegion] = [regions[0]]
    for region in regions[1:]:
        previous = merged[-1]
        same_type = region.statement_type == previous.statement_type
        adjacent = region.page_start == previous.page_end + 1
        if not (same_type and adjacent):
            merged.append(region)
            continue
        continued = "EXPLICIT_CONTINUATION" in region.reason_codes
        both_other = previous.statement_type == StatementType.OTHER_FINANCIAL_STATEMENT
        # Adjacent headed statements (GROUP then BANK, 6M then quarter) stay separate.
        if continued or both_other:
            merged[-1] = StatementRegion(
                region_id=previous.region_id,
                statement_type=previous.statement_type,
                page_start=previous.page_start,
                page_end=region.page_end,
                heading_text=previous.heading_text,
                source_refs=previous.source_refs + region.source_refs,
                reason_codes=tuple(dict.fromkeys((*previous.reason_codes, *region.reason_codes))),
            )
        else:
            merged.append(region)
    return tuple(merged)
