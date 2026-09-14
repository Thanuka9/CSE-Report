from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.diagnostics.bakeoffs import (
    continuation_census,
    g01_unlabelled_entity_census,
    header_h0_metrics,
)
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import canonical_document_from_pages, geometric_document


def test_h0_two_column_company_quarter_resolves_entity_period_unit() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "1,000"), (340.0, "900")),
        )
    )
    statement = bind_column_context(document, build_statements(document)[0])
    metrics = header_h0_metrics((statement,))
    assert metrics["entity_resolved"] >= 1
    assert metrics["period_resolved"] >= 1
    assert metrics["duration_resolved"] >= 1
    assert metrics["unit_resolved"] >= 1


def test_g01_does_not_copy_issuer_metadata_into_unlabelled_columns() -> None:
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
    )
    census = g01_unlabelled_entity_census(document, (statement,))
    assert all(column.entity_scope is None for column in statement.columns)
    assert census["unresolved_entity_columns"] >= 1


def test_g05_explicit_marker_is_required() -> None:
    continued = canonical_document_from_pages(
        (
            ("Statement of profit or loss", "Revenue 100"),
            ("Statement of profit or loss (continued)", "Profit for the period 60"),
        )
    )
    unmarked = canonical_document_from_pages(
        (
            ("Statement of profit or loss", "Revenue 100"),
            ("Operating expenses 40", "Other commentary"),
        )
    )
    assert continuation_census(continued)["explicit_continuation_regions"] >= 1
    assert continuation_census(unmarked)["explicit_continuation_regions"] == 0
    assert detect_statement_regions(unmarked)[0].page_end == 1


def test_g09_eps_note_without_group_currently_infers_company() -> None:
    """Current production rule. Absence of Group is not source-confirmed Company evidence."""

    document = geometric_document(
        (
            ((40.0, "30 June 2026"), (300.0, "30 June 2025")),
            ((40.0, "Basic earnings per share"), (300.0, "1.46"), (420.0, "1.10")),
        ),
        title="INVESTOR INFORMATION",
    )
    statement = bind_column_context(document, build_statements(document)[0])
    assert statement.statement_type.value == "EPS_NOTE"
    assert all(column.entity_scope is EntityScope.COMPANY for column in statement.columns)


def test_period_ended_without_months_does_not_invent_duration() -> None:
    document = geometric_document(
        (
            ((40.0, "GROUP"), (220.0, "GROUP"), (340.0, "COMPANY"), (460.0, "COMPANY")),
            (
                (40.0, "For The Period Ended 30 June 2026"),
                (220.0, "30 June 2025"),
                (340.0, "30 June 2026"),
                (460.0, "30 June 2025"),
            ),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "100"),
                (220.0, "90"),
                (340.0, "80"),
                (460.0, "70"),
            ),
        )
    )
    statement = bind_column_context(document, build_statements(document)[0])
    assert all(column.duration_months is None for column in statement.columns)
