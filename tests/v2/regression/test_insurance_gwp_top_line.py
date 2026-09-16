"""Permanent regression: insurance Gross written contribution is TOP_LINE."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import EntityScope, StatementType
from cse_financial_etl.v2.contracts.statement import StatementRow
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher
from tests.v2.helpers import geometric_document


def test_gross_written_contribution_matches_top_line_alias() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Gross written contribution (premium)"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code == "TOP_LINE"


def test_gross_written_contribution_publishes_group_current_quarter() -> None:
    document = geometric_document(
        (
            ((40.0, "GROUP"), (300.0, "COMPANY")),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs."),),
            (
                (40.0, "Gross written contribution (premium)"),
                (200.0, "3,974,507,328"),
                (360.0, "1,924,597,263"),
            ),
        ),
        title="STATEMENT OF PROFIT OR LOSS",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="ATL.N0000"
    )
    top = [
        fact
        for fact in facts
        if fact.metric_code == "TOP_LINE"
        and fact.entity_scope is EntityScope.GROUP
        and fact.normalized_value == Decimal("3974507328")
    ]
    assert top
    assert top[0].duration_months == 3
