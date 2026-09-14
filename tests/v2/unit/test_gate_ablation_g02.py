from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.diagnostics.gate_ablation import g02_ablation
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import geometric_document


def test_g02_default_cascade_matches_bind_default() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    result = g02_ablation(document, issuer_id="issuer-1", expected_entity_scope=EntityScope.COMPANY)
    statement = build_statements(document)[0]
    bound = bind_column_context(document, statement)
    assert bound.columns
    assert result["cascade_source_facts"] >= 1
    assert result["facts_suppressed_by_cascade"] >= 0
