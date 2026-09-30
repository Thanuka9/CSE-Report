"""Persist every numeric candidate, including those that never become SourceFacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from json import dumps
from pathlib import Path
from typing import Any

import polars as pl

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import (
    EntityScope,
    FirstFailureStage,
    PublicationStatus,
)
from cse_financial_etl.v2.contracts.facts import FactCandidate, SourceFact
from cse_financial_etl.v2.contracts.investigation import (
    CandidateTrace,
    ConceptAlternativeRecord,
)
from cse_financial_etl.v2.contracts.statement import CanonicalStatement
from cse_financial_etl.v2.resolution.production_selection import production_selection_outcome
from cse_financial_etl.v2.resolution.resolver import source_admission_failure
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry


def first_failure_for_fact(fact: SourceFact) -> FirstFailureStage:
    if fact.validation_status.value == "FAILED":
        return FirstFailureStage.VALIDATION
    if fact.publication_status is PublicationStatus.WITHHELD:
        return FirstFailureStage.PUBLICATION
    return FirstFailureStage.NONE


def _evidence_text(refs: Sequence[object]) -> str | None:
    parts = [str(getattr(ref, "raw_text", "") or "") for ref in refs]
    parts = [part for part in parts if part]
    return " | ".join(parts) if parts else None


def _concept_alternatives(candidate: FactCandidate) -> tuple[ConceptAlternativeRecord, ...]:
    rows: list[ConceptAlternativeRecord] = []
    alternatives = candidate.concept_alternatives or (
        (candidate.concept,) if candidate.concept is not None else ()
    )
    primary = candidate.concept.metric_code if candidate.concept is not None else None
    for item in alternatives:
        if item is None:
            continue
        rejection = None
        if item.metric_code is None:
            rejection = "ABSTAIN"
        elif candidate.concept_status.value != "RESOLVED":
            rejection = "UNRESOLVED_OR_AMBIGUOUS"
        elif item.metric_code != primary:
            rejection = "NOT_PRIMARY"
        rows.append(
            ConceptAlternativeRecord(
                metric_code=item.metric_code,
                match_kind=item.match_kind.value,
                matched_alias=item.matched_alias,
                source_concept=item.source_concept,
                score=item.score,
                rejection_reason=rejection,
                accounting_regime=None
                if item.accounting_regime is None
                else item.accounting_regime.value,
            )
        )
    return tuple(rows)


def build_candidate_traces(
    candidates: Sequence[FactCandidate],
    source_facts: Sequence[SourceFact],
    *,
    statements: Sequence[CanonicalStatement] = (),
    document: CanonicalDocument | None = None,
    issuer_id: str,
    filing_version_id: str,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    selected_fact_ids: set[str] | None = None,
    run_id: str | None = None,
    code_sha: str | None = None,
    sector: str | None = None,
    regime: str | None = None,
    registry: ConceptRegistry | None = None,
) -> tuple[CandidateTrace, ...]:
    registry = registry or load_registry()
    facts_by_candidate = {fact.fact_id.replace("-fact", "-cand"): fact for fact in source_facts}
    rows_by_id = {row.row_id: row for statement in statements for row in statement.rows}
    columns_by_id = {
        column.column_id: column for statement in statements for column in statement.columns
    }
    statement_by_id = {statement.statement_id: statement for statement in statements}
    page_mode = {}
    if document is not None:
        page_mode = {
            page.page_number: page.extraction_mode.value for page in document.pages
        }
    selected_ids = selected_fact_ids or set()
    traces: list[CandidateTrace] = []
    for candidate in candidates:
        fact = facts_by_candidate.get(candidate.candidate_id)
        admission = source_admission_failure(candidate, registry=registry)
        if fact is None:
            stage = admission or FirstFailureStage.CONCEPT_UNRESOLVED
            publication = None
            validation = None
            reasons = candidate.reason_codes
        else:
            stage = first_failure_for_fact(fact)
            publication = fact.publication_status
            validation = fact.validation_status
            reasons = fact.reason_codes
        selected, selection_status, selection_reason = production_selection_outcome(
            fact,
            expected_entity=expected_entity_scope,
            period_end=target_period_end,
            selected_ids=selected_ids,
        )
        row = rows_by_id.get(candidate.row_id)
        column = columns_by_id.get(candidate.column_id)
        statement = statement_by_id.get(candidate.statement_id)
        alternatives = _concept_alternatives(candidate)
        concept_codes = tuple(
            item.metric_code for item in alternatives if item.metric_code is not None
        )
        page_class = page_mode.get(candidate.source_ref.page_number)
        header_refs: tuple[object, ...] = ()
        if column is not None:
            header_refs = column.entity_evidence + column.period_evidence
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
                statement_type=None if statement is None else statement.statement_type.value,
                table_id=None if statement is None else statement.statement_id,
                candidate_id=candidate.candidate_id,
                row_id=candidate.row_id,
                row_label=row.raw_label if row is not None else "",
                cell_id=candidate.cell_id,
                source_fact_id=None if fact is None else fact.fact_id,
                raw_numeric_text=candidate.source_ref.raw_text,
                parsed_numeric_value=candidate.raw_value,
                page_classification=page_class,
                page_classification_status=page_class,
                statement_detection_status=(
                    "NOT_DETECTED" if statement is None else "DETECTED"
                ),
                table_detection_status="NOT_DETECTED" if statement is None else "DETECTED",
                table_reconstruction_status=(
                    "EMPTY"
                    if statement is None or not statement.rows
                    else "RECONSTRUCTED"
                ),
                row_reconstruction_status="MISSING" if row is None else "RECONSTRUCTED",
                concept_candidates=concept_codes,
                concept_alternatives=alternatives,
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
                header_evidence=_evidence_text(header_refs),
                unit_evidence=_evidence_text(() if column is None else column.unit_evidence),
                duration_evidence=_evidence_text(
                    () if column is None else column.duration_evidence
                ),
                comparison_evidence=_evidence_text(
                    () if column is None else column.comparison_evidence
                ),
                reason_codes=reasons,
                source_fact_created=fact is not None,
                validation_status=validation,
                production_selection_status=selection_status,
                production_selected=selected,
                production_selection_reason=selection_reason,
                publication_status=publication,
                first_failure_stage=stage,
            )
        )
    return tuple(traces)


def write_candidate_trace(
    path: Path,
    traces: Sequence[CandidateTrace],
    identity: Mapping[str, Any] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for trace in traces:
        payload = trace.model_dump(mode="json")
        if identity:
            payload = {**identity, **payload}
        payload["concept_candidates"] = dumps(list(payload["concept_candidates"]))
        payload["concept_alternatives"] = dumps(payload["concept_alternatives"])
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
