"""Copy signed review decisions onto native V2 facts used by the OFFICIAL workbook.

Production review stamps V1-shaped ExtractedFact rows. The V2 workbook is rendered
from native SourceFact/DerivedFact objects created at extraction time. Without this
propagation, OFFICIAL mode drops valid facts that were approved on the V1-shaped rows.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import EntityScope, ReviewStatus
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact

SIGNED_REVIEW = frozenset(
    {ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.CURATED}
)

_ENTITY_TO_V1 = {
    EntityScope.COMPANY: "COMPANY",
    EntityScope.BANK: "BANK",
    EntityScope.GROUP: "GROUP",
    EntityScope.CONSOLIDATED: "GROUP",
    EntityScope.SEPARATE: "COMPANY",
}


def evidence_json_for_native(fact_id: str) -> str:
    """Stable ExtractedFact evidence payload that retains the native V2 fact_id."""

    return json.dumps(
        {"evidence_grade": "DETERMINISTIC", "v2_fact_id": fact_id},
        separators=(",", ":"),
        sort_keys=True,
    )


def v2_fact_id_from_extracted(fact: ExtractedFact) -> str | None:
    raw = fact.evidence_json
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    fact_id = parsed.get("v2_fact_id")
    if fact_id is None or str(fact_id).strip() == "":
        return None
    return str(fact_id)


def _signed_status(value: str | ReviewStatus | None) -> ReviewStatus | None:
    if value is None:
        return None
    try:
        status = ReviewStatus(str(value).strip().upper())
    except ValueError:
        return None
    if status in SIGNED_REVIEW:
        return status
    return None


def _extracted_identity(fact: ExtractedFact) -> tuple[Any, ...]:
    value = fact.normalized_value
    period = fact.period_end.isoformat() if fact.period_end is not None else ""
    return (
        str(fact.symbol or "").strip().upper(),
        period,
        str(fact.metric_code or ""),
        str(fact.entity_scope or ""),
        str(fact.comparison_role or ""),
        fact.duration_months,
        str(value) if value is not None else "",
    )


def _native_identity(fact: SourceFact | DerivedFact) -> tuple[Any, ...]:
    entity = _ENTITY_TO_V1.get(fact.entity_scope, str(fact.entity_scope))
    comparison = (
        fact.comparison_role.value
        if hasattr(fact.comparison_role, "value")
        else str(fact.comparison_role)
    )
    value = fact.normalized_value
    return (
        str(fact.issuer_id or "").strip().upper(),
        fact.period_end.isoformat(),
        str(fact.metric_code or ""),
        entity,
        comparison,
        fact.duration_months,
        str(value) if value is not None else "",
    )


def propagate_review_status_to_native_facts(
    extracted: Sequence[ExtractedFact],
    source_facts: Sequence[SourceFact],
    derived_facts: Sequence[DerivedFact],
) -> tuple[tuple[SourceFact, ...], tuple[DerivedFact, ...]]:
    """Stamp APPROVED/REJECTED/CURATED from ExtractedFact onto matching natives.

    Matching prefers ``evidence_json.v2_fact_id``. Identity
    (symbol, period, metric, entity, comparison, duration, value) is the fallback
    when a fact_id is absent. REVIEW is not a signed decision and is not copied.
    """

    by_id: dict[str, ReviewStatus] = {}
    by_identity: dict[tuple[Any, ...], ReviewStatus] = {}
    for extracted_fact in extracted:
        status = _signed_status(extracted_fact.review_status)
        if status is None:
            continue
        fact_id = v2_fact_id_from_extracted(extracted_fact)
        if fact_id:
            by_id[fact_id] = status
        by_identity[_extracted_identity(extracted_fact)] = status

    updated_source: list[SourceFact] = []
    for source_native in source_facts:
        status = by_id.get(source_native.fact_id) or by_identity.get(
            _native_identity(source_native)
        )
        if status is None or source_native.review_status == status:
            updated_source.append(source_native)
        else:
            updated_source.append(
                source_native.model_copy(update={"review_status": status})
            )

    updated_derived: list[DerivedFact] = []
    for derived_native in derived_facts:
        status = by_id.get(derived_native.fact_id) or by_identity.get(
            _native_identity(derived_native)
        )
        if status is None or derived_native.review_status == status:
            updated_derived.append(derived_native)
        else:
            updated_derived.append(
                derived_native.model_copy(update={"review_status": status})
            )

    return tuple(updated_source), tuple(updated_derived)
