"""Persist every numeric candidate, including those that never become SourceFacts."""

from __future__ import annotations

from collections.abc import Sequence
from json import dumps
from pathlib import Path

import polars as pl

from cse_financial_etl.v2.contracts.enums import (
    EntityScope,
    FirstFailureStage,
    PublicationStatus,
)
from cse_financial_etl.v2.contracts.facts import FactCandidate, SourceFact
from cse_financial_etl.v2.contracts.investigation import CandidateTrace
from cse_financial_etl.v2.contracts.statement import CanonicalStatement
from cse_financial_etl.v2.resolution.resolver import source_admission_failure
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry


def first_failure_for_fact(fact: SourceFact) -> FirstFailureStage:
    if fact.validation_status.value == "FAILED":
        return FirstFailureStage.VALIDATION
    if fact.publication_status is PublicationStatus.WITHHELD:
        return FirstFailureStage.PUBLICATION
    return FirstFailureStage.NONE


def build_candidate_traces(
    candidates: Sequence[FactCandidate],
    source_facts: Sequence[SourceFact],
    *,
    statements: Sequence[CanonicalStatement] = (),
    issuer_id: str,
    filing_version_id: str,
    expected_entity_scope: EntityScope | None = None,
    run_id: str | None = None,
    code_sha: str | None = None,
    sector: str | None = None,
    regime: str | None = None,
    registry: ConceptRegistry | None = None,
) -> tuple[CandidateTrace, ...]:
    registry = registry or load_registry()
    facts_by_candidate = {
        fact.fact_id.replace("-fact", "-cand"): fact for fact in source_facts
    }
    rows_by_id = {row.row_id: row for statement in statements for row in statement.rows}
    statement_type_by_id = {
        statement.statement_id: statement.statement_type.value for statement in statements
    }
    traces: list[CandidateTrace] = []
    for candidate in candidates:
        fact = facts_by_candidate.get(candidate.candidate_id)
        admission = source_admission_failure(
            candidate,
            expected_entity_scope=expected_entity_scope,
            registry=registry,
        )
        if fact is None:
            stage = admission or FirstFailureStage.CONCEPT_UNRESOLVED
            production_selected = False
            publication = None
            validation = None
            reasons = candidate.reason_codes
        else:
            stage = first_failure_for_fact(fact)
            production_selected = fact.publication_status is not PublicationStatus.WITHHELD
            publication = fact.publication_status
            validation = fact.validation_status
            reasons = fact.reason_codes
        row = rows_by_id.get(candidate.row_id)
        concept_codes: tuple[str, ...] = ()
        if candidate.concept is not None and candidate.concept.metric_code:
            concept_codes = (candidate.concept.metric_code,)
        traces.append(
            CandidateTrace(
                run_id=run_id,
                code_sha=code_sha,
                pdf_sha=candidate.source_ref.source_sha256,
                filing_version_id=filing_version_id,
                issuer_id=issuer_id,
                sector=sector,
                regime=regime,
                page=candidate.source_ref.page_number,
                statement_id=candidate.statement_id,
                statement_type=statement_type_by_id.get(candidate.statement_id),
                row_id=candidate.row_id,
                row_label=row.raw_label if row is not None else "",
                cell_id=candidate.cell_id,
                raw_numeric_text=candidate.source_ref.raw_text,
                parsed_numeric_value=candidate.raw_value,
                concept_candidates=concept_codes,
                concept_status=candidate.concept_status,
                entity_status=candidate.entity_status,
                period_status=candidate.period_status,
                duration_status=candidate.duration_status,
                comparison_status=candidate.comparison_status,
                unit_status=candidate.unit_status,
                resolved_metric=candidate.concept.metric_code if candidate.concept else None,
                entity_scope=candidate.entity_scope,
                period_end=candidate.period_end,
                duration_months=candidate.duration_months,
                comparison_role=candidate.comparison_role,
                currency=candidate.currency,
                scale=candidate.monetary_scale,
                unit_dimension=candidate.unit_dimension,
                source_ref_sha256=candidate.source_ref.source_sha256,
                reason_codes=reasons,
                source_fact_created=fact is not None,
                validation_status=validation,
                production_selected=production_selected,
                publication_status=publication,
                first_failure_stage=stage,
            )
        )
    return tuple(traces)


def write_candidate_trace(path: Path, traces: Sequence[CandidateTrace]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for trace in traces:
        payload = trace.model_dump(mode="json")
        payload["concept_candidates"] = dumps(list(payload["concept_candidates"]))
        payload["reason_codes"] = dumps(list(payload["reason_codes"]))
        payload["extra"] = dumps(payload["extra"], sort_keys=True)
        for key, value in payload.items():
            if value is None:
                payload[key] = ""
        rows.append(payload)
    frame = (
        pl.DataFrame(rows, infer_schema_length=len(rows))
        if rows
        else pl.DataFrame({"pdf_sha": []})
    )
    frame.write_parquet(path)
