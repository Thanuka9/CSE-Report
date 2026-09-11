"""Regressions for AS_AT facts versus exact-quarter FLOW context."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.contracts.publication import publishability_decision
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.transformation.ratios import derive_ratio_facts


def _fact(metric: str, value: str, *, role: str | None, duration: int | None) -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        period_end=date(2026, 6, 30),
        metric_code=metric,
        metric_type="STOCK" if metric.startswith("TOTAL_") else "MONETARY_ABSOLUTE",
        raw_text=value,
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line=metric,
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
        comparison_role=role,
        duration_months=duration,
        validation_status="PASSED",
        review_status="APPROVED",
        overall_certainty=0.99,
    )


def test_as_at_stock_does_not_need_comparison_role_to_be_publishable() -> None:
    fact = _fact("TOTAL_ASSETS", "300", role=None, duration=None)
    assert publishability_decision(fact, release_mode="DRAFT") == (True, None)


def test_debt_to_equity_accepts_same_period_as_at_inputs_without_flow_role() -> None:
    liabilities = _fact("TOTAL_LIABILITIES", "200", role=None, duration=None)
    equity = _fact("TOTAL_EQUITY", "100", role=None, duration=None)
    derived = derive_ratio_facts([(object(), [liabilities, equity])], display_periods=[date(2026, 6, 30)])
    debt_to_equity = next(f for f in derived[0][1] if f.metric_code == "DEBT_TO_EQUITY")
    assert debt_to_equity.normalized_value == Decimal("2")


def test_flow_ratio_input_still_requires_current_three_month_context() -> None:
    pat = _fact("PAT", "10", role="COMPARATIVE", duration=3)
    equity = _fact("TOTAL_EQUITY", "100", role=None, duration=None)
    derived = derive_ratio_facts([(object(), [pat, equity])], display_periods=[date(2026, 6, 30)])
    roe = next(f for f in derived[0][1] if f.metric_code == "ROE")
    assert roe.normalized_value is None
    assert roe.status in {"INSUFFICIENT_INPUT", "INCOMPATIBLE_PERIOD_CONTEXT"}
