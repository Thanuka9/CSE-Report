"""V2 filing pipeline. Isolated from V1 production orchestration."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import AccountingRegime, EntityScope
from cse_financial_etl.v2.contracts.facts import DerivedFact, FactCandidate, SourceFact
from cse_financial_etl.v2.contracts.investigation import CandidateTrace
from cse_financial_etl.v2.contracts.statement import CanonicalStatement
from cse_financial_etl.v2.diagnostics.candidate_trace import (
    build_candidate_traces,
    write_candidate_trace,
)
from cse_financial_etl.v2.diagnostics.stage_metrics import StageMetrics
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.resolution.column_context import (
    bind_column_context,
    context_resolution_metrics,
)
from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts
from cse_financial_etl.v2.resolution.resolver import build_candidates, resolve_source_facts
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.statements.table_reconstructor import reconstruct_statements
from cse_financial_etl.v2.taxonomy.matcher import accounting_regime_for
from cse_financial_etl.v2.validation.accounting import derive_facts, validate_source_facts


@dataclass(frozen=True)
class FilingPipelineResult:
    """Exact in-run artefacts. Callers must not rebuild candidates for traces."""

    statements: tuple[CanonicalStatement, ...]
    candidates: tuple[FactCandidate, ...]
    source_facts: tuple[SourceFact, ...]
    derived_facts: tuple[DerivedFact, ...]
    stage_metrics: StageMetrics
    production_selected_source: tuple[SourceFact, ...] = ()
    production_selected_derived: tuple[DerivedFact, ...] = ()
    traces: tuple[CandidateTrace, ...] = ()
    document: CanonicalDocument | None = None

    def __iter__(self) -> Iterator[Any]:
        yield self.statements
        yield self.source_facts
        yield self.derived_facts
        yield self.stage_metrics

    def __getitem__(self, index: int) -> Any:
        return (
            self.statements,
            self.source_facts,
            self.derived_facts,
            self.stage_metrics,
        )[index]


def run_filing_pipeline(
    document: CanonicalDocument,
    *,
    issuer_id: str,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    accounting_regime: AccountingRegime | None = None,
    issuer_name: str = "",
    issuer_type: str = "",
    candidate_trace_path: Path | None = None,
    run_id: str | None = None,
    code_sha: str | None = None,
) -> FilingPipelineResult:
    regime = accounting_regime or accounting_regime_for(
        issuer_id=issuer_id, issuer_name=issuer_name, issuer_type=issuer_type
    )
    regions = detect_statement_regions(document)
    reconstructed = reconstruct_statements(document, regions)
    statements = tuple(
        bind_column_context(
            document,
            statement,
            expected_entity_scope=expected_entity_scope,
            target_period_end=target_period_end,
        )
        for statement in reconstructed
    )
    candidates = tuple(
        candidate
        for statement in statements
        for candidate in build_candidates(statement, accounting_regime=regime)
    )
    source = resolve_source_facts(
        candidates,
        issuer_id=issuer_id,
        filing_version_id=document.filing_version_id,
    )
    validated = validate_source_facts(source)
    derived = derive_facts(validated)
    query_applied = expected_entity_scope is not None or target_period_end is not None
    if query_applied:
        selected_source = select_pipeline_facts(
            validated,
            period_end=target_period_end,
            expected_entity=expected_entity_scope,
        )
        selected_derived = select_pipeline_facts(
            derived,
            period_end=target_period_end,
            expected_entity=expected_entity_scope,
        )
    else:
        selected_source = ()
        selected_derived = ()
    traces = build_candidate_traces(
        candidates,
        validated,
        statements=statements,
        document=document,
        issuer_id=issuer_id,
        filing_version_id=document.filing_version_id,
        expected_entity_scope=expected_entity_scope,
        target_period_end=target_period_end,
        selected_fact_ids={fact.fact_id for fact in selected_source} if query_applied else set(),
        run_id=run_id,
        code_sha=code_sha,
        regime=None if regime is None else regime.value,
    )
    if candidate_trace_path is not None:
        write_candidate_trace(candidate_trace_path, traces)
    context_counts = {
        "entity_resolved_candidates": 0,
        "period_resolved_candidates": 0,
        "unit_resolved_candidates": 0,
    }
    for statement in statements:
        metrics = context_resolution_metrics(statement)
        context_counts["entity_resolved_candidates"] += metrics["entity_resolved"]
        context_counts["period_resolved_candidates"] += metrics["period_resolved"]
        context_counts["unit_resolved_candidates"] += metrics["unit_resolved"]
    stage = StageMetrics(
        documents_parsed=1,
        statements_detected=len(regions),
        source_numeric_cells=sum(
            len(row.cells) for statement in statements for row in statement.rows
        ),
        concept_candidates=len(candidates),
        entity_resolved_candidates=context_counts["entity_resolved_candidates"],
        period_resolved_candidates=context_counts["period_resolved_candidates"],
        unit_resolved_candidates=context_counts["unit_resolved_candidates"],
        source_facts=len(validated),
        validated_facts=sum(item.validation_status.value == "PASSED" for item in validated),
        draft_eligible_facts=sum(item.publication_status.value == "ELIGIBLE" for item in validated),
    )
    return FilingPipelineResult(
        statements=statements,
        candidates=candidates,
        source_facts=validated,
        derived_facts=derived,
        stage_metrics=stage,
        production_selected_source=selected_source,
        production_selected_derived=selected_derived,
        traces=traces,
        document=document,
    )


def run_pdf_pipeline(
    pdf_path: Path,
    *,
    issuer_id: str,
    filing_version_id: str,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    force_ocr: bool = False,
    accounting_regime: AccountingRegime | None = None,
    issuer_name: str = "",
    issuer_type: str = "",
    candidate_trace_path: Path | None = None,
    run_id: str | None = None,
    code_sha: str | None = None,
) -> FilingPipelineResult:
    document = read_document(pdf_path, filing_version_id=filing_version_id, force_ocr=force_ocr)
    return run_filing_pipeline(
        document,
        issuer_id=issuer_id,
        expected_entity_scope=expected_entity_scope,
        target_period_end=target_period_end,
        accounting_regime=accounting_regime,
        issuer_name=issuer_name,
        issuer_type=issuer_type,
        candidate_trace_path=candidate_trace_path,
        run_id=run_id,
        code_sha=code_sha,
    )
