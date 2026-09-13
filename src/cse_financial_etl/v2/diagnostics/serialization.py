"""Serialize V2 facts for replay/shadow without losing identity fields."""

from __future__ import annotations

from collections.abc import Mapping

from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact


def source_fact_to_mapping(fact: SourceFact) -> dict[str, object]:
    return {
        "filing_version_id": fact.filing_version_id,
        "issuer_id": fact.issuer_id,
        "entity_scope": fact.entity_scope.value,
        "period_end": fact.period_end.isoformat(),
        "duration_months": fact.duration_months,
        "comparison_role": fact.comparison_role.value,
        "metric_code": fact.metric_code,
        "normalized_value": str(fact.normalized_value),
        "raw_value": str(fact.raw_value),
        "validation_status": fact.validation_status.value,
        "review_status": fact.review_status.value,
        "publication_status": fact.publication_status.value,
        "parser_path": fact.source_ref.parser_name,
        "reason_codes": ",".join(fact.reason_codes),
        "cell_id": fact.cell_id,
        "source_sha256": fact.source_ref.source_sha256,
    }


def derived_fact_to_mapping(fact: DerivedFact) -> dict[str, object]:
    return {
        "issuer_id": fact.issuer_id,
        "entity_scope": fact.entity_scope.value,
        "period_end": fact.period_end.isoformat(),
        "duration_months": fact.duration_months,
        "comparison_role": fact.comparison_role.value,
        "metric_code": fact.metric_code,
        "normalized_value": str(fact.normalized_value),
        "validation_status": fact.validation_status.value,
        "review_status": fact.review_status.value,
        "publication_status": fact.publication_status.value,
        "formula_id": fact.formula_id,
        "input_fact_ids": ",".join(fact.input_fact_ids),
        "fact_kind": fact.fact_kind.value,
    }


def mapping_sort_key(payload: Mapping[str, object]) -> tuple[str, ...]:
    return (
        str(payload.get("filing_version_id") or ""),
        str(payload.get("metric_code") or ""),
        str(payload.get("entity_scope") or ""),
        str(payload.get("period_end") or ""),
        str(payload.get("duration_months") or ""),
        str(payload.get("comparison_role") or ""),
        str(payload.get("cell_id") or ""),
    )
