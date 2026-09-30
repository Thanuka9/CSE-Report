"""Map V2 SourceFacts onto the V1 ExtractedFact shape used by the production pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.config import infer_entity_scope
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import EntityScope, ReviewStatus, ValidationStatus
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
from cse_financial_etl.v2.production.review_propagation import evidence_json_for_native
from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry

_ENTITY_TO_V1 = {
    EntityScope.COMPANY: "COMPANY",
    EntityScope.BANK: "BANK",
    EntityScope.GROUP: "GROUP",
    EntityScope.CONSOLIDATED: "GROUP",
    EntityScope.SEPARATE: "COMPANY",
}


@dataclass(frozen=True, slots=True)
class V2ProductionExtraction:
    production_facts: list[ExtractedFact]
    source_facts: tuple[SourceFact, ...]
    derived_facts: tuple[DerivedFact, ...]


def extract_filing_v2_bundle(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    *,
    issuers: dict[str, Any] | None = None,
) -> V2ProductionExtraction:
    """Run V2 extraction and return both native facts and V1-shaped pipeline rows."""

    _statements, source, derived, _metrics = run_pdf_pipeline(
        pdf_path,
        issuer_id=symbol,
        filing_version_id=f"{symbol}-{period_end.isoformat()}",
        target_period_end=period_end,
        issuer_name=issuer_name,
        v1_baseline_facts=True,
        issuers=issuers,
    )
    expected = _expected_entity(issuer_name, issuers)
    source = select_pipeline_facts(source, period_end=period_end, expected_entity=expected)
    derived = select_pipeline_facts(derived, period_end=period_end, expected_entity=expected)
    registry = load_registry()
    rows: list[ExtractedFact] = []
    for source_fact in source:
        rows.append(
            _from_source(source_fact, issuer_name=issuer_name, symbol=symbol, registry=registry)
        )
    for derived_fact in derived:
        rows.append(
            _from_derived(derived_fact, issuer_name=issuer_name, symbol=symbol, registry=registry)
        )
    return V2ProductionExtraction(
        production_facts=rows,
        source_facts=tuple(source),
        derived_facts=tuple(derived),
    )


def write_v2_native_sidecar(path: Path, bundle: V2ProductionExtraction) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_facts": [fact.model_dump(mode="json") for fact in bundle.source_facts],
        "derived_facts": [fact.model_dump(mode="json") for fact in bundle.derived_facts],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_v2_native_sidecar(path: Path) -> tuple[tuple[SourceFact, ...], tuple[DerivedFact, ...]]:
    if not path.exists():
        return (), ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    source = tuple(SourceFact.model_validate(item) for item in payload.get("source_facts") or ())
    derived = tuple(DerivedFact.model_validate(item) for item in payload.get("derived_facts") or ())
    return source, derived


def extract_filing_v2(
    pdf_path: Path,
    issuer_name: str,
    symbol: str,
    period_end: date,
    *,
    issuers: dict[str, Any] | None = None,
    v2_native_sidecar: Path | None = None,
) -> list[ExtractedFact]:
    """Run the V2 orchestrator with the V1 extractor as the baseline backend.

    Native V2 recovery may add or replace a fact only with stronger PDF evidence.
    A valid V1 baseline fact is preserved otherwise. GROUP is never relabelled
    COMPANY.
    """

    bundle = extract_filing_v2_bundle(
        pdf_path, issuer_name, symbol, period_end, issuers=issuers
    )
    if v2_native_sidecar is not None:
        write_v2_native_sidecar(v2_native_sidecar, bundle)
    return bundle.production_facts



def synchronize_native_governance(
    source_facts: tuple[SourceFact, ...] | list[SourceFact],
    derived_facts: tuple[DerivedFact, ...] | list[DerivedFact],
    production_facts: list[ExtractedFact],
) -> tuple[tuple[SourceFact, ...], tuple[DerivedFact, ...]]:
    """Copy validated/reviewed governance state back onto native V2 facts.

    The V1-shaped rows are the objects stamped by equation validation and signed review
    decisions in the production pipeline. The V2 workbook, however, renders native
    SourceFact/DerivedFact objects. Propagation is therefore required, but it must be
    fail-closed: issuer, metric, period, entity and normalized value must all match, and
    conflicting production governance states never choose a winner.
    """

    governance: dict[
        tuple[str, str, date, str, Decimal],
        set[tuple[ValidationStatus, ReviewStatus]],
    ] = {}
    for production_fact in production_facts:
        if production_fact.normalized_value is None:
            continue
        try:
            validation = ValidationStatus(
                str(production_fact.validation_status).strip().upper()
            )
            review = ReviewStatus(str(production_fact.review_status).strip().upper())
        except ValueError:
            continue
        key = (
            production_fact.symbol.strip().upper(),
            production_fact.metric_code.strip().upper(),
            production_fact.period_end,
            production_fact.entity_scope.strip().upper(),
            production_fact.normalized_value,
        )
        governance.setdefault(key, set()).add((validation, review))

    def state_for(fact: SourceFact | DerivedFact) -> tuple[ValidationStatus, ReviewStatus] | None:
        entity = _ENTITY_TO_V1.get(fact.entity_scope, fact.entity_scope.value)
        key = (
            fact.issuer_id.strip().upper(),
            fact.metric_code.strip().upper(),
            fact.period_end,
            entity,
            fact.normalized_value,
        )
        states = governance.get(key, set())
        if len(states) != 1:
            return None
        return next(iter(states))

    synced_source: list[SourceFact] = []
    for source_fact in source_facts:
        state = state_for(source_fact)
        if state is None:
            synced_source.append(source_fact)
            continue
        validation, review = state
        synced_source.append(
            source_fact.model_copy(
                update={
                    "validation_status": validation,
                    "review_status": review,
                }
            )
        )

    synced_derived: list[DerivedFact] = []
    for derived_fact in derived_facts:
        state = state_for(derived_fact)
        if state is None:
            synced_derived.append(derived_fact)
            continue
        validation, review = state
        synced_derived.append(
            derived_fact.model_copy(
                update={
                    "validation_status": validation,
                    "review_status": review,
                }
            )
        )
    return tuple(synced_source), tuple(synced_derived)


def _expected_entity(issuer_name: str, issuers: dict[str, Any] | None) -> EntityScope | None:
    label = infer_entity_scope(issuer_name, issuers)
    try:
        return EntityScope(str(label).strip().upper())
    except ValueError:
        return None


def _from_source(
    fact: SourceFact,
    *,
    issuer_name: str,
    symbol: str,
    registry: ConceptRegistry,
) -> ExtractedFact:
    concept = registry.get(fact.metric_code)
    scale = fact.source_scale or Decimal("1")
    method = "V2_COLUMN_CONTEXT"
    reasons = fact.reason_codes
    if "V1_BASELINE_PRESERVED" in reasons or (
        "V1_BASELINE" in reasons and "V2_SUPERSEDES_V1" not in reasons
    ):
        method = "V1_BASELINE"
    elif "V2_SUPERSEDES_V1" in reasons:
        method = "V2_SUPERSEDES_V1"
    elif "V1_V2_AGREE" in reasons:
        method = "V1_V2_AGREE"
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
        confidence="DETERMINISTIC",
        status="EXTRACTED",
        raw_label=fact.source_ref.raw_text,
        source_bbox=None if fact.source_ref.bbox is None else str(fact.source_ref.bbox),
        extraction_method=method,
        semantic_model="v2-registry",
        certainty_band="DETERMINISTIC",
        evidence_json=evidence_json_for_native(fact.fact_id),
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
    concept = registry.get(fact.metric_code)
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
        confidence="DETERMINISTIC",
        status="EXTRACTED",
        raw_label=fact.formula_id,
        extraction_method="V2_DERIVED",
        semantic_model="v2-derived",
        certainty_band="DETERMINISTIC",
        evidence_json=evidence_json_for_native(fact.fact_id),
        comparison_role=fact.comparison_role.value,
        duration_months=fact.duration_months,
        validation_status=fact.validation_status.value,
        review_status=fact.review_status.value,
    )
