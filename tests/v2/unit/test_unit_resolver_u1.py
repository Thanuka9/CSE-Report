"""U1 scoped unit resolver unit tests. Production default remains U0."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import EntityScope, UnitDimension
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.resolution.resolver import build_candidates
from cse_financial_etl.v2.resolution.unit_u1 import resolve_scoped_unit, unit_u1_census
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import geometric_document


def test_u1_per_share_does_not_inherit_table_thousands() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Basic earnings per share (Rs.)"), (220.0, "1.46")),
        ),
        title="INVESTOR INFORMATION",
    )
    statement = bind_column_context(document, build_statements(document)[0])
    assert statement.columns[0].monetary_scale == Decimal("1000")
    row = statement.rows[0]
    currency, scale, dimension, status, _reasons = resolve_scoped_unit(
        metric_code="EPS_BASIC",
        row=row,
        column=statement.columns[0],
        statement=statement,
        document=document,
    )
    assert dimension is UnitDimension.PER_SHARE
    assert status.value == "RESOLVED"
    assert scale == Decimal("1")
    assert currency == "LKR"


def test_u1_build_candidates_opt_in() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Basic earnings per share (Rs.)"), (220.0, "2.00")),
        ),
        title="INVESTOR INFORMATION",
    )
    statement = bind_column_context(document, build_statements(document)[0])
    u0 = build_candidates(statement, document=document, unit_engine="U0")
    u1 = build_candidates(statement, document=document, unit_engine="U1")
    census = unit_u1_census(u1)
    assert census["per_share_with_thousands_scale"] == 0
    # U0 may still carry statement thousands on the candidate before SourceFact clamp.
    assert any(
        item.monetary_scale == Decimal("1000")
        for item in u0
        if item.unit_dimension is UnitDimension.PER_SHARE
    ) or not any(item.unit_dimension is UnitDimension.PER_SHARE for item in u0)
    assert all(
        item.monetary_scale in {None, Decimal("1"), Decimal("0.01")}
        for item in u1
        if item.unit_dimension is UnitDimension.PER_SHARE
    )


def test_u1_does_not_require_query_entity() -> None:
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
    candidates = build_candidates(statement, document=document, unit_engine="U1")
    assert candidates
    assert all(item.entity_scope is None for item in candidates)
