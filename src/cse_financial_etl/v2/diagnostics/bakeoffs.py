"""H0/U0/G01/G03/G05 diagnostic bake-offs. Prototypes H2/U2/P2 are not built."""

from __future__ import annotations

from collections import Counter
from typing import Any

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import PeriodBehavior, PublicationStatus
from cse_financial_etl.v2.contracts.facts import SourceFact
from cse_financial_etl.v2.contracts.statement import CanonicalStatement
from cse_financial_etl.v2.diagnostics.lineage import audit_source_fact
from cse_financial_etl.v2.diagnostics.real_filings import RealFilingCase
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.resolution.column_context import (
    _cover_heading,
    context_resolution_metrics,
    parse_entity_scope,
    parse_unit,
)
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.taxonomy.registry import load_registry


def header_h0_metrics(statements: tuple[CanonicalStatement, ...]) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for statement in statements:
        totals.update(context_resolution_metrics(statement))
    return dict(totals)


def g03_flow_census(facts: tuple[SourceFact, ...]) -> dict[str, int]:
    registry = load_registry()
    counts: Counter[str] = Counter()
    for fact in facts:
        concept = registry.get(fact.metric_code)
        if concept.period_behavior is not PeriodBehavior.FLOW:
            continue
        counts["flow_source_facts"] += 1
        if fact.duration_months is None:
            counts["flow_duration_missing"] += 1
        elif fact.duration_months == 3:
            counts["flow_duration_quarter"] += 1
        else:
            counts["flow_duration_non_quarter"] += 1
        if "EXACT_QUARTER_NOT_REPORTED" in fact.reason_codes:
            counts["exact_quarter_gate"] += 1
    return dict(counts)


def g01_unlabelled_entity_census(
    document: CanonicalDocument,
    statements: tuple[CanonicalStatement, ...],
) -> dict[str, Any]:
    cover_entity = parse_entity_scope(_cover_heading(document))
    unresolved = 0
    document_cue_unused = 0
    for statement in statements:
        for column in statement.columns:
            if column.entity_scope is None:
                unresolved += 1
                if cover_entity is not None:
                    document_cue_unused += 1
    return {
        "unresolved_entity_columns": unresolved,
        "document_heading_entity": None if cover_entity is None else cover_entity.value,
        "unresolved_with_document_entity_cue": document_cue_unused,
        "note": (
            "Document-heading entity is not copied into columns. "
            "Issuer metadata is not source evidence. GROUP is never COMPANY."
        ),
    }


def continuation_census(document: CanonicalDocument) -> dict[str, int]:
    regions = detect_statement_regions(document)
    explicit = sum(1 for region in regions if "EXPLICIT_CONTINUATION" in region.reason_codes)
    return {
        "regions": len(regions),
        "explicit_continuation_regions": explicit,
    }


def unit_u0_census(statements: tuple[CanonicalStatement, ...]) -> dict[str, int]:
    unresolved = 0
    cents = 0
    usd = 0
    for statement in statements:
        for column in statement.columns:
            if column.unit_dimension is None:
                unresolved += 1
            blob = " ".join(ref.raw_text or "" for ref in column.unit_evidence)
            if "cent" in blob.casefold():
                cents += 1
            parsed = parse_unit(blob)
            if parsed[0] == "USD":
                usd += 1
    return {
        "unit_unresolved_columns": unresolved,
        "cents_evidence_columns": cents,
        "usd_columns": usd,
    }


def g08_duplicate_eligible_census(facts: tuple[SourceFact, ...]) -> dict[str, int]:
    eligible = [
        fact for fact in facts if fact.publication_status is PublicationStatus.ELIGIBLE
    ]
    keys = Counter(
        (
            fact.metric_code,
            fact.entity_scope.value,
            fact.period_end.isoformat(),
            fact.duration_months,
            fact.comparison_role.value,
        )
        for fact in eligible
    )
    return {
        "eligible_source_facts": len(eligible),
        "duplicate_identity_groups": sum(1 for count in keys.values() if count > 1),
    }


def pipeline_bakeoff(case: RealFilingCase, document: CanonicalDocument) -> dict[str, Any]:
    statements, source, _derived, _metrics = run_filing_pipeline(
        document,
        issuer_id=case.issuer_id,
        expected_entity_scope=case.entity_scope,
        target_period_end=case.period_end,
        issuer_name=case.issuer_name,
        issuer_type=case.issuer_type,
    )
    lineage = Counter(
        audit_source_fact(fact, document=document, expected_pdf_sha=document.source_sha256).value
        for fact in source
    )
    return {
        "case_id": case.case_id,
        "source_fact_count": len(source),
        "lineage": dict(lineage),
        "h0": header_h0_metrics(statements),
        "u0": unit_u0_census(statements),
        "g01": g01_unlabelled_entity_census(document, statements),
        "g03": g03_flow_census(source),
        "g05": continuation_census(document),
        "g08": g08_duplicate_eligible_census(source),
        "h2_built": False,
        "u2_built": False,
        "p2_built": False,
    }
