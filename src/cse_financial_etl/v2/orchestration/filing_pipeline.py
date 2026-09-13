"""V2 filing pipeline. Isolated from V1 production orchestration."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import AccountingRegime, EntityScope
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact
from cse_financial_etl.v2.contracts.statement import CanonicalStatement
from cse_financial_etl.v2.diagnostics.stage_metrics import StageMetrics
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.resolution.column_context import (
    bind_column_context,
    context_resolution_metrics,
)
from cse_financial_etl.v2.resolution.resolver import build_candidates, resolve_source_facts
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.statements.table_reconstructor import reconstruct_statements
from cse_financial_etl.v2.taxonomy.matcher import accounting_regime_for
from cse_financial_etl.v2.validation.accounting import derive_facts, validate_source_facts


def run_filing_pipeline(
    document: CanonicalDocument,
    *,
    issuer_id: str,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    accounting_regime: AccountingRegime | None = None,
    issuer_name: str = "",
    issuer_type: str = "",
) -> tuple[
    tuple[CanonicalStatement, ...], tuple[SourceFact, ...], tuple[DerivedFact, ...], StageMetrics
]:
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
        expected_entity_scope=expected_entity_scope,
    )
    validated = validate_source_facts(source)
    derived = derive_facts(validated)
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
    return statements, validated, derived, stage


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
) -> tuple[
    tuple[CanonicalStatement, ...], tuple[SourceFact, ...], tuple[DerivedFact, ...], StageMetrics
]:
    document = read_document(pdf_path, filing_version_id=filing_version_id, force_ocr=force_ocr)
    return run_filing_pipeline(
        document,
        issuer_id=issuer_id,
        expected_entity_scope=expected_entity_scope,
        target_period_end=target_period_end,
        accounting_regime=accounting_regime,
        issuer_name=issuer_name,
        issuer_type=issuer_type,
    )
