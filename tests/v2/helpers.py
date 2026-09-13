"""Shared builders for V2 contract tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.v2.contracts.document import (
    CanonicalDocument,
    CanonicalLine,
    CanonicalPage,
    CanonicalToken,
)
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    ExtractionMode,
    PublicationStatus,
    ReleaseMode,
    ReviewStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import SourceFact
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.contracts.release import ReleaseContext

VALID_SHA = "a" * 64


def source_ref(**overrides: object) -> SourceRef:
    payload: dict[str, object] = {
        "filing_id": "filing-1",
        "filing_version_id": "fv-1",
        "source_sha256": VALID_SHA,
        "page_number": 1,
        "bbox": (10.0, 20.0, 110.0, 36.0),
        "raw_text": "1,234",
        "parser_name": "v2.native_pymupdf",
        "parser_version": "1.0.0",
    }
    payload.update(overrides)
    return SourceRef.model_validate(payload)


def release_context(**overrides: object) -> ReleaseContext:
    payload: dict[str, object] = {
        "generation_id": "gen-1",
        "run_id": "run-1",
        "mode": ReleaseMode.DRAFT,
        "code_sha": "abc123",
        "policy_hash": "policy-1",
        "source_snapshot_id": "snap-1",
    }
    payload.update(overrides)
    return ReleaseContext.model_validate(payload)


def source_fact(**overrides: object) -> SourceFact:
    payload: dict[str, object] = {
        "fact_id": "fact-1",
        "filing_version_id": "fv-1",
        "statement_id": "stmt-1",
        "cell_id": "cell-1",
        "issuer_id": "issuer-1",
        "metric_code": "PAT",
        "entity_scope": EntityScope.COMPANY,
        "period_end": date(2026, 6, 30),
        "duration_months": 3,
        "comparison_role": ComparisonRole.CURRENT,
        "raw_value": Decimal("1234"),
        "normalized_value": Decimal("1234000"),
        "currency": "LKR",
        "source_scale": Decimal("1000"),
        "unit_dimension": UnitDimension.MONETARY,
        "source_ref": source_ref(),
        "validation_status": ValidationStatus.PASSED,
        "review_status": ReviewStatus.REVIEW,
        "publication_status": PublicationStatus.ELIGIBLE,
    }
    payload.update(overrides)
    return SourceFact.model_validate(payload)


def canonical_document_from_pages(
    pages: tuple[tuple[str, ...], ...],
    *,
    filing_version_id: str = "fv-1",
) -> CanonicalDocument:
    """Build a CanonicalDocument from page heading/body lines (one string per line)."""

    canonical_pages: list[CanonicalPage] = []
    for page_number, lines in enumerate(pages, start=1):
        canonical_lines: list[CanonicalLine] = []
        y = 40.0
        for line_index, text in enumerate(lines):
            token = CanonicalToken(
                text=text,
                page_number=page_number,
                bbox=(40.0, y, 40.0 + max(12.0, len(text) * 6.0), y + 10.0),
                source_parser="v2.test",
            )
            canonical_lines.append(
                CanonicalLine(
                    line_id=f"p{page_number}:l{line_index:04d}",
                    tokens=(token,),
                    bbox=token.bbox,
                )
            )
            y += 14.0
        canonical_pages.append(
            CanonicalPage(
                page_number=page_number,
                width=612.0,
                height=792.0,
                lines=tuple(canonical_lines),
                extraction_mode=ExtractionMode.NATIVE,
            )
        )
    return CanonicalDocument(
        filing_version_id=filing_version_id,
        source_sha256=VALID_SHA,
        pages=tuple(canonical_pages),
        parser_manifest={"parser_name": "v2.test", "parser_version": "1.0.0"},
    )


def geometric_document(
    rows: tuple[tuple[tuple[float, str], ...], ...],
    *,
    filing_version_id: str = "fv-1",
    title: str = "Statement of profit or loss",
) -> CanonicalDocument:
    """Build a one-page statement with explicit token x positions."""

    lines: list[CanonicalLine] = []
    y = 40.0
    title_token = CanonicalToken(
        text=title,
        page_number=1,
        bbox=(40.0, y, 400.0, y + 10.0),
        source_parser="v2.test",
    )
    lines.append(CanonicalLine(line_id="p1:l0000", tokens=(title_token,), bbox=title_token.bbox))
    y = 70.0
    for index, cells in enumerate(rows, start=1):
        tokens = tuple(
            CanonicalToken(
                text=text,
                page_number=1,
                bbox=(x, y, x + max(12.0, len(text) * 6.0), y + 10.0),
                source_parser="v2.test",
            )
            for x, text in cells
        )
        bbox = (
            min(token.bbox[0] for token in tokens),
            min(token.bbox[1] for token in tokens),
            max(token.bbox[2] for token in tokens),
            max(token.bbox[3] for token in tokens),
        )
        lines.append(CanonicalLine(line_id=f"p1:l{index:04d}", tokens=tokens, bbox=bbox))
        y += 16.0
    page = CanonicalPage(
        page_number=1,
        width=612.0,
        height=792.0,
        lines=tuple(lines),
        extraction_mode=ExtractionMode.NATIVE,
    )
    return CanonicalDocument(
        filing_version_id=filing_version_id,
        source_sha256=VALID_SHA,
        pages=(page,),
        parser_manifest={"parser_name": "v2.test", "parser_version": "1.0.0"},
    )
