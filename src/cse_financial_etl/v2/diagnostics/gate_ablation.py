"""G02 partial-context cascade ablation. Diagnostic; production default stays cascade."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.resolution.resolver import build_candidates, resolve_source_facts
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.statements.table_reconstructor import reconstruct_statements


def count_source_facts(
    document: CanonicalDocument,
    *,
    issuer_id: str,
    expected_entity_scope: EntityScope | None = None,
    partial_monetary: str,
) -> int:
    regions = detect_statement_regions(document)
    reconstructed = reconstruct_statements(document, regions)
    statements = tuple(
        bind_column_context(
            document,
            statement,
            expected_entity_scope=expected_entity_scope,
            partial_monetary=partial_monetary,  # type: ignore[arg-type]
        )
        for statement in reconstructed
    )
    candidates = tuple(
        candidate for statement in statements for candidate in build_candidates(statement)
    )
    facts = resolve_source_facts(
        candidates,
        issuer_id=issuer_id,
        filing_version_id=document.filing_version_id,
        expected_entity_scope=expected_entity_scope,
    )
    return len(facts)


def g02_ablation(
    document: CanonicalDocument,
    *,
    issuer_id: str,
    expected_entity_scope: EntityScope | None = None,
) -> dict[str, int]:
    cascade = count_source_facts(
        document,
        issuer_id=issuer_id,
        expected_entity_scope=expected_entity_scope,
        partial_monetary="cascade",
    )
    per_column = count_source_facts(
        document,
        issuer_id=issuer_id,
        expected_entity_scope=expected_entity_scope,
        partial_monetary="per_column",
    )
    return {
        "cascade_source_facts": cascade,
        "per_column_source_facts": per_column,
        "facts_suppressed_by_cascade": max(0, per_column - cascade),
    }
