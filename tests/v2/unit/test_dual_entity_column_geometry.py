"""Generalized dual-entity column geometry regressions (entity ownership P0).

No issuer identity in production code paths. These synthetics prove:
- Group|Company headers bind to distinct monetary columns
- Group-only stays GROUP (never forced COMPANY)
- Bank|Group stays BANK/GROUP (never forced BANK as COMPANY)
- Unlabelled monetary columns remain entity-unresolved
"""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.resolution.column_context import bind_column_context
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import geometric_document


def test_group_company_six_column_layout_binds_company_current() -> None:
    """Group/Company × current/prior/change — Company current must not inherit GROUP."""

    document = geometric_document(
        (
            ((200.0, "Group"), (340.0, "Company")),
            (
                (40.0, "For Three Months Ended 31 December"),
                (180.0, "2025"),
                (220.0, "2024"),
                (260.0, "Change"),
                (320.0, "2025"),
                (360.0, "2024"),
                (400.0, "Change"),
            ),
            ((40.0, "Rs.'000"),),
            (
                (40.0, "Profit from Operations"),
                (180.0, "6,791,657"),
                (220.0, "4,621,485"),
                (260.0, "47"),
                (320.0, "274,634"),
                (360.0, "205,888"),
                (400.0, "33"),
            ),
            (
                (40.0, "Basic Earnings Per Share(Rs.)"),
                (180.0, "191.31"),
                (220.0, "102.06"),
                (320.0, "10.33"),
                (360.0, "6.79"),
            ),
        ),
        title="Statement of Income",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="SYNTH.N0000", issuer_type="INSURANCE"
    )
    company_op = [
        f
        for f in facts
        if f.metric_code == "OPERATING_PROFIT"
        and f.entity_scope is EntityScope.COMPANY
        and f.normalized_value == Decimal("274634000")
    ]
    company_eps = [
        f
        for f in facts
        if f.metric_code == "EPS_BASIC"
        and f.entity_scope is EntityScope.COMPANY
        and f.normalized_value == Decimal("10.33")
    ]
    assert company_op, "COMPANY operating profit current must survive beside GROUP columns"
    assert company_eps, "COMPANY EPS current must survive beside GROUP columns"
    assert all(f.duration_months == 3 for f in company_op + company_eps)


def test_group_only_banner_never_forced_to_company() -> None:
    document = geometric_document(
        (
            ((200.0, "Group"),),
            ((40.0, "For the three months ended 31 December 2025"),),
            ((40.0, "Rs.'000"),),
            ((40.0, "Profit for the Period"), (220.0, "79,190")),
        ),
        title="Statement of Profit or Loss",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="SYNTH.N0000", issuer_type="GENERAL"
    )
    pats = [f for f in facts if f.metric_code == "PAT"]
    assert pats
    assert all(f.entity_scope is EntityScope.GROUP for f in pats)
    assert not any(f.entity_scope is EntityScope.COMPANY for f in pats)


def test_bank_group_layout_never_forces_bank_from_group() -> None:
    document = geometric_document(
        (
            ((180.0, "Bank"), (320.0, "Group")),
            ((40.0, "For the three months ended 31 December 2025"),),
            ((40.0, "LKR '000"),),
            (
                (40.0, "Profit before VAT on financial services"),
                (180.0, "748,922"),
                (320.0, "1,840,423"),
            ),
        ),
        title="Statement of Profit or Loss",
    )
    statements = build_statements(document)
    bound = bind_column_context(document, statements[0])
    scopes = [c.entity_scope for c in bound.columns if c.entity_scope is not None]
    assert EntityScope.BANK in scopes
    assert EntityScope.GROUP in scopes
    # GROUP column must remain GROUP — never rewritten to BANK.
    assert any(c.entity_scope is EntityScope.GROUP for c in bound.columns)


def test_unlabelled_monetary_columns_remain_entity_unresolved() -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 31 December 2025"),),
            ((40.0, "Rs.'000"),),
            ((40.0, "Profit for the Period"), (220.0, "100"), (320.0, "90")),
        ),
        title="Statement of Profit or Loss",
    )
    statements = build_statements(document)
    bound = bind_column_context(document, statements[0])
    assert all(c.entity_scope is None for c in bound.columns)


def test_sofp_group_company_company_current_assets_survive() -> None:
    document = geometric_document(
        (
            ((200.0, "Group"), (300.0, "Group"), (400.0, "Company"), (500.0, "Company")),
            (
                (40.0, "As at 31 December"),
                (200.0, "2025"),
                (300.0, "2024"),
                (400.0, "2025"),
                (500.0, "2024"),
            ),
            ((40.0, "Rs.'000"),),
            (
                (40.0, "Total Assets"),
                (200.0, "18,370,368"),
                (300.0, "16,406,468"),
                (400.0, "10,163,485"),
                (500.0, "9,298,839"),
            ),
        ),
        title="Statement of Financial Position",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="SYNTH.N0000", issuer_type="GENERAL"
    )
    company = [
        f
        for f in facts
        if f.metric_code == "TOTAL_ASSETS"
        and f.entity_scope is EntityScope.COMPANY
        and f.normalized_value == Decimal("10163485000")
        and f.comparison_role is ComparisonRole.CURRENT
    ]
    assert company, "COMPANY SOFP total assets must survive beside GROUP columns"
