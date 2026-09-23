"""Adapt proven V1 ExtractedFact rows into V2 SourceFacts.

This is a fact-level adapter, not a 200k-cell discovery dump. Only EXTRACTED
source metrics with a numeric value become baseline facts. Derived V1 rows are
omitted so V2 can re-derive them under V2 governance.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    PeriodBehavior,
    PublicationStatus,
    ResolutionStatus,
    ReviewStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import SourceFact
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry

V1_PARSER_NAME = "v1.statement_extractor"
V1_PARSER_VERSION = "baseline"
_SKIP_CODES = frozenset({"EPS_SELECTED"})
_ENTITY = {
    "COMPANY": EntityScope.COMPANY,
    "BANK": EntityScope.BANK,
    "GROUP": EntityScope.GROUP,
    "CONSOLIDATED": EntityScope.CONSOLIDATED,
    "SEPARATE": EntityScope.SEPARATE,
}
_COMPARISON = {
    "CURRENT": ComparisonRole.CURRENT,
    "COMPARATIVE": ComparisonRole.COMPARATIVE,
}
_UNIT_FROM_METRIC_TYPE = {
    "MONETARY_ABSOLUTE": UnitDimension.MONETARY,
    "MONETARY_PER_SHARE": UnitDimension.PER_SHARE,
    "RATIO": UnitDimension.RATIO,
    "COUNT": UnitDimension.COUNT,
    "PERCENTAGE": UnitDimension.PERCENTAGE,
}


def extract_v1_baseline_facts(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    *,
    source_sha256: str,
    filing_version_id: str,
    issuers: dict[str, Any] | None = None,
    registry: ConceptRegistry | None = None,
) -> tuple[SourceFact, ...]:
    """Run the proven V1 extractor and return V2-shaped baseline source facts."""

    from cse_financial_etl.extraction.statement_extractor import extract_filing as extract_filing_v1

    rows = extract_filing_v1(
        pdf_path,
        issuer_name,
        symbol,
        period_end,
        issuers=issuers,
    )
    return tuple(
        fact
        for fact in (
            v1_extracted_to_source_fact(
                row,
                source_sha256=source_sha256,
                filing_version_id=filing_version_id,
                issuer_id=symbol,
                registry=registry,
            )
            for row in rows
        )
        if fact is not None
    )


def v1_extracted_to_source_fact(
    row: ExtractedFact,
    *,
    source_sha256: str,
    filing_version_id: str,
    issuer_id: str,
    registry: ConceptRegistry | None = None,
) -> SourceFact | None:
    """Map one V1 EXTRACTED fact. Returns None when the row is not a baseline source."""

    if row.status != "EXTRACTED":
        return None
    if row.metric_code in _SKIP_CODES:
        return None
    if row.normalized_value is None:
        return None
    entity = _ENTITY.get((row.entity_scope or "").upper())
    if entity is None:
        return None
    concepts = registry or load_registry()
    try:
        concept = concepts.get(row.metric_code)
    except KeyError:
        return None
    comparison = _COMPARISON.get((row.comparison_role or "").upper(), ComparisonRole.CURRENT)
    duration = row.duration_months
    if concept.period_behavior in {PeriodBehavior.POINT_IN_TIME, PeriodBehavior.STOCK}:
        duration = None
    unit = concept.unit_dimension
    if row.metric_type:
        unit = _UNIT_FROM_METRIC_TYPE.get(row.metric_type.upper(), unit)
    page = row.source_page if row.source_page and row.source_page >= 1 else 1
    bbox = _parse_bbox(row.source_bbox)
    raw_value = row.raw_value if row.raw_value is not None else row.normalized_value
    scale = Decimal(str(row.scale_factor)) if row.scale_factor else Decimal("1")
    reasons = ["V1_BASELINE"]
    if row.source_page is None:
        reasons.append("V1_PAGE_DEFAULT")
    if bbox is None:
        reasons.append("V1_BBOX_ABSENT")
    return SourceFact(
        fact_id=f"v1-{issuer_id}-{row.metric_code}-{row.period_end.isoformat()}-{uuid4().hex[:8]}",
        filing_version_id=filing_version_id,
        statement_id="v1-baseline",
        cell_id=f"v1-cell-{row.metric_code}-{page}",
        issuer_id=issuer_id,
        metric_code=row.metric_code,
        source_concept=row.raw_label or row.source_line,
        matched_alias=row.raw_label,
        entity_scope=entity,
        period_end=row.period_end,
        duration_months=duration,
        comparison_role=comparison,
        raw_value=Decimal(str(raw_value)),
        normalized_value=Decimal(str(row.normalized_value)),
        currency=row.currency or "LKR",
        source_scale=scale,
        unit_dimension=unit,
        source_ref=SourceRef(
            filing_id=issuer_id,
            filing_version_id=filing_version_id,
            source_sha256=source_sha256,
            page_number=page,
            bbox=bbox,
            raw_text=row.raw_text or row.source_line,
            parser_name=V1_PARSER_NAME,
            parser_version=V1_PARSER_VERSION,
        ),
        validation_status=ValidationStatus.NOT_VALIDATED,
        review_status=ReviewStatus.REVIEW,
        publication_status=PublicationStatus.ELIGIBLE,
        duration_status=(
            ResolutionStatus.NOT_APPLICABLE
            if duration is None
            else ResolutionStatus.RESOLVED
        ),
        reason_codes=tuple(reasons),
    )


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, (list, tuple)) and len(payload) == 4:
        x0, y0, x1, y1 = (float(item) for item in payload)
    elif isinstance(payload, dict):
        try:
            x0 = float(payload["x0"])
            y0 = float(payload["y0"])
            x1 = float(payload["x1"])
            y1 = float(payload["y1"])
        except (KeyError, TypeError, ValueError):
            return None
    else:
        return None
    if x1 < x0 or y1 < y0:
        return None
    return (x0, y0, x1, y1)
