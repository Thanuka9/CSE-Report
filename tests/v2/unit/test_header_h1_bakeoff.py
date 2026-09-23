"""H1 header engine bake-off unit tests. Production default remains H0."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.diagnostics.bakeoffs import header_h0_metrics, header_h1_metrics
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import geometric_document


def test_h1_resolves_company_quarter_without_query_context() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "1,000"), (340.0, "900")),
        )
    )
    statement = bind_column_context(document, build_statements(document)[0], header_engine="H1")
    metrics = header_h1_metrics((statement,))
    assert metrics["entity_resolved"] >= 1
    assert metrics["period_resolved"] >= 1
    assert metrics["duration_resolved"] >= 1
    assert all(
        column.entity_scope in {None, EntityScope.COMPANY} for column in statement.columns
    )


def test_h1_does_not_copy_expected_entity_into_unlabelled_columns() -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    statement = bind_column_context(
        document,
        build_statements(document)[0],
        expected_entity_scope=EntityScope.COMPANY,
        header_engine="H1",
    )
    assert all(column.entity_scope is None for column in statement.columns)


def test_h1_composes_year_only_columns_with_shared_header_day_month() -> None:
    """Year leaves + one shared DATE phrase complete period_end (LITE-like)."""

    document = geometric_document(
        (
            ((40.0, "Group"),),
            ((220.0, "Quarter Ended"), (340.0, "Quarter Ended")),
            ((220.0, "2025"), (340.0, "2024")),
            ((40.0, "31st December 2025"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "100"), (340.0, "90")),
        )
    )
    statement = bind_column_context(document, build_statements(document)[0], header_engine="H1")
    periods = [column.period_end for column in statement.columns if column.period_end is not None]
    assert periods, "expected year+day-month composition"
    assert any(column.entity_scope is EntityScope.GROUP for column in statement.columns)


def test_h0_default_unchanged_on_bind() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "1,000"), (340.0, "900")),
        )
    )
    h0 = bind_column_context(document, build_statements(document)[0])
    assert header_h0_metrics((h0,))["entity_resolved"] >= 1
