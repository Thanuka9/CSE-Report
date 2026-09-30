"""Lineage and derived-fact audits. Every emitted fact must be reproducible."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from cse_financial_etl.facts.derived_facts import compute_quarter_ratios
from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import (
    DerivedAuditStatus,
    LineageStatus,
    PeriodBehavior,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.statements.numeric import parse_numeric, split_label_and_values
from cse_financial_etl.v2.taxonomy.registry import load_registry


def audit_source_fact(
    fact: SourceFact,
    *,
    document: CanonicalDocument | None = None,
    expected_pdf_sha: str | None = None,
) -> LineageStatus:
    ref = fact.source_ref
    pdf_sha = expected_pdf_sha or (document.source_sha256 if document is not None else None)
    if pdf_sha is not None and ref.source_sha256 != pdf_sha:
        return LineageStatus.LINEAGE_INCOMPLETE
    if document is not None:
        pages = {page.page_number for page in document.pages}
        if ref.page_number not in pages:
            return LineageStatus.LINEAGE_INCOMPLETE
    if ref.bbox is None or not (ref.raw_text or "").strip():
        return LineageStatus.LINEAGE_INCOMPLETE
    if not _raw_value_reproducible(fact):
        return LineageStatus.SOURCE_VALUE_NOT_REPRODUCIBLE
    scale = fact.source_scale or Decimal("1")
    expected_normalized = (
        fact.raw_value * scale
        if fact.unit_dimension is UnitDimension.MONETARY
        else fact.raw_value
    )
    if expected_normalized != fact.normalized_value:
        return LineageStatus.NORMALIZATION_ERROR
    registry = load_registry()
    concept = registry.get(fact.metric_code)
    if fact.entity_status.value != "RESOLVED" or fact.period_status.value != "RESOLVED":
        return LineageStatus.CONTEXT_EVIDENCE_INCOMPLETE
    if fact.unit_status.value != "RESOLVED":
        return LineageStatus.CONTEXT_EVIDENCE_INCOMPLETE
    if concept.period_behavior is PeriodBehavior.FLOW and fact.duration_months is None:
        return LineageStatus.CONTEXT_EVIDENCE_INCOMPLETE
    return LineageStatus.LINEAGE_COMPLETE


def _raw_value_reproducible(fact: SourceFact) -> bool:
    text = fact.source_ref.raw_text or ""
    if parse_numeric(text) == fact.raw_value:
        return True
    _label, values = split_label_and_values(text)
    return any(parse_numeric(item) == fact.raw_value for item in values)


def audit_derived_fact(
    fact: DerivedFact,
    source_facts: Sequence[SourceFact],
) -> DerivedAuditStatus:
    by_id = {item.fact_id: item for item in source_facts}
    inputs = tuple(by_id.get(item_id) for item_id in fact.input_fact_ids)
    if any(item is None for item in inputs):
        return DerivedAuditStatus.INPUT_MISSING
    proven = tuple(item for item in inputs if item is not None)
    if any(
        item.entity_scope != fact.entity_scope or item.period_end != fact.period_end
        for item in proven
    ):
        return DerivedAuditStatus.CONTEXT_MISMATCH
    if fact.metric_code == "EPS_SELECTED":
        expected = proven[0].normalized_value
        if expected == fact.normalized_value:
            return DerivedAuditStatus.DERIVED_COMPLETE
        return DerivedAuditStatus.FORMULA_MISMATCH
    by_code = {item.metric_code: item for item in proven}
    # Derived ratio audit needs the full sibling set, not only formula inputs.
    siblings = {
        item.metric_code: item
        for item in source_facts
        if item.issuer_id == fact.issuer_id
        and item.entity_scope == fact.entity_scope
        and item.period_end == fact.period_end
    }
    by_code = {**siblings, **by_code}
    ratios = compute_quarter_ratios(
        pat=_optional(by_code, "PAT"),
        equity=_optional(by_code, "TOTAL_EQUITY"),
        assets=_optional(by_code, "TOTAL_ASSETS"),
        liabilities=_optional(by_code, "TOTAL_LIABILITIES"),
        top_line=_optional(by_code, "TOP_LINE"),
    )
    mapping = {
        "LIABILITIES_TO_EQUITY": "DEBT_TO_EQUITY",
        "ROE": "ROE",
        "ROA": "ROA",
        "NPM": "NPM",
    }
    wanted = mapping.get(fact.metric_code)
    if wanted is None:
        return DerivedAuditStatus.FORMULA_MISMATCH
    match = next((item for item in ratios if item.code == wanted), None)
    if match is None or match.value is None or match.value != fact.normalized_value:
        return DerivedAuditStatus.FORMULA_MISMATCH
    return DerivedAuditStatus.DERIVED_COMPLETE


def _optional(by_code: dict[str, SourceFact], code: str) -> Decimal | None:
    fact = by_code.get(code)
    return None if fact is None else fact.normalized_value
