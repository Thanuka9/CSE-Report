"""Map V2 SourceFacts onto the V1 ExtractedFact shape used by the production pipeline."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.config import infer_entity_scope
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    PublicationStatus,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry

_ENTITY_TO_V1 = {
    EntityScope.COMPANY: "COMPANY",
    EntityScope.BANK: "BANK",
    EntityScope.GROUP: "GROUP",
    EntityScope.CONSOLIDATED: "GROUP",
    EntityScope.SEPARATE: "COMPANY",
}

_ENTITY_EQUIVALENTS: dict[EntityScope, frozenset[EntityScope]] = {
    EntityScope.COMPANY: frozenset({EntityScope.COMPANY, EntityScope.SEPARATE}),
    EntityScope.SEPARATE: frozenset({EntityScope.COMPANY, EntityScope.SEPARATE}),
    EntityScope.GROUP: frozenset({EntityScope.GROUP, EntityScope.CONSOLIDATED}),
    EntityScope.CONSOLIDATED: frozenset({EntityScope.GROUP, EntityScope.CONSOLIDATED}),
    EntityScope.BANK: frozenset({EntityScope.BANK}),
}


def extract_filing_v2(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    *,
    issuers: dict[str, Any] | None = None,
) -> list[ExtractedFact]:
    """Run the V2 column-owned extractor and emit production ExtractedFact rows.

    Query targets select among already-proven facts. They never invent entity,
    period, or unit, and GROUP is never relabelled COMPANY.
    """

    _statements, source, derived, _metrics = run_pdf_pipeline(
        pdf_path,
        issuer_id=symbol,
        filing_version_id=f"{symbol}-{period_end.isoformat()}",
        target_period_end=period_end,
    )
    expected = _expected_entity(issuer_name, issuers)
    source = select_pipeline_facts(source, period_end=period_end, expected_entity=expected)
    derived = select_pipeline_facts(derived, period_end=period_end, expected_entity=expected)
    registry = load_registry()
    rows: list[ExtractedFact] = []
    for fact in source:
        rows.append(_from_source(fact, issuer_name=issuer_name, symbol=symbol, registry=registry))
    for fact in derived:
        rows.append(_from_derived(fact, issuer_name=issuer_name, symbol=symbol, registry=registry))
    return rows


def select_pipeline_facts[TFact: SourceFact | DerivedFact](
    facts: tuple[TFact, ...] | list[TFact],
    *,
    period_end: date,
    expected_entity: EntityScope | None,
) -> tuple[TFact, ...]:
    """Keep current-period eligible facts for the production snapshot query.

    If the requested entity exists among eligible facts, only that entity is
    forwarded. If it does not, remaining facts keep their true entity labels.
    """

    eligible = [
        fact
        for fact in facts
        if fact.publication_status is PublicationStatus.ELIGIBLE
        and fact.comparison_role is ComparisonRole.CURRENT
        and fact.period_end == period_end
        and (fact.duration_months is None or fact.duration_months == 3)
    ]
    if expected_entity is not None:
        matching = [fact for fact in eligible if _entity_matches(fact.entity_scope, expected_entity)]
        if matching:
            eligible = matching
    return _unique_by_metric(eligible)


def _expected_entity(issuer_name: str, issuers: dict[str, Any] | None) -> EntityScope | None:
    label = infer_entity_scope(issuer_name, issuers)
    try:
        return EntityScope(str(label).strip().upper())
    except ValueError:
        return None


def _entity_matches(actual: EntityScope, expected: EntityScope) -> bool:
    return actual in _ENTITY_EQUIVALENTS.get(expected, frozenset({expected}))


def _unique_by_metric[TFact: SourceFact | DerivedFact](facts: list[TFact]) -> tuple[TFact, ...]:
    chosen: dict[str, TFact] = {}
    for fact in facts:
        existing = chosen.get(fact.metric_code)
        if existing is None or _fact_rank(fact) < _fact_rank(existing):
            chosen[fact.metric_code] = fact
    return tuple(chosen[code] for code in sorted(chosen))


def _fact_rank(fact: SourceFact | DerivedFact) -> tuple[int, int, str]:
    page = getattr(getattr(fact, "source_ref", None), "page_number", 10**6)
    return (int(page), 0, fact.fact_id)


def _from_source(
    fact: SourceFact,
    *,
    issuer_name: str,
    symbol: str,
    registry: ConceptRegistry,
) -> ExtractedFact:
    concept = registry.get(fact.metric_code)  # type: ignore[union-attr]
    scale = fact.source_scale or Decimal("1")
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=fact.period_end,
        metric_code=fact.metric_code,
        metric_type=concept.metric_type,
        raw_text=fact.source_ref.raw_text,
        raw_value=fact.raw_value,
        normalized_value=fact.normalized_value,
        currency=fact.currency,
        scale_factor=int(scale),
        entity_scope=_ENTITY_TO_V1[fact.entity_scope],
        source_page=fact.source_ref.page_number,
        source_line=fact.source_ref.raw_text,
        unit_source_text=fact.source_ref.raw_text,
        confidence="HIGH",
        status="EXTRACTED",
        raw_label=fact.source_ref.raw_text,
        source_bbox=None if fact.source_ref.bbox is None else str(fact.source_ref.bbox),
        extraction_method="V2_COLUMN_CONTEXT",
        semantic_model="v2-registry",
        semantic_confidence=1.0,
        entity_confidence=1.0,
        period_confidence=1.0,
        unit_confidence=1.0,
        overall_certainty=1.0,
        certainty_band="HIGH",
        comparison_role=fact.comparison_role.value,
        duration_months=fact.duration_months,
        validation_status=fact.validation_status.value,
        review_status=fact.review_status.value,
    )


def _from_derived(
    fact: DerivedFact,
    *,
    issuer_name: str,
    symbol: str,
    registry: ConceptRegistry,
) -> ExtractedFact:
    concept = registry.get(fact.metric_code)  # type: ignore[union-attr]
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=fact.period_end,
        metric_code=fact.metric_code,
        metric_type=concept.metric_type,
        raw_text=None,
        raw_value=fact.normalized_value,
        normalized_value=fact.normalized_value,
        currency="LKR",
        scale_factor=1,
        entity_scope=_ENTITY_TO_V1[fact.entity_scope],
        source_page=None,
        source_line=fact.formula_id,
        unit_source_text=None,
        confidence="HIGH",
        status="EXTRACTED",
        raw_label=fact.formula_id,
        extraction_method="V2_DERIVED",
        semantic_model="v2-derived",
        comparison_role=fact.comparison_role.value,
        duration_months=fact.duration_months,
        validation_status=fact.validation_status.value,
        review_status=fact.review_status.value,
    )
