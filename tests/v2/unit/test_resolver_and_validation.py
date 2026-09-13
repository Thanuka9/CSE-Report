from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import (
    EntityScope,
    PublicationStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from cse_financial_etl.v2.validation.accounting import derive_facts, validate_source_facts
from tests.v2.helpers import geometric_document, source_fact


def test_pipeline_emits_pat_with_lineage_and_does_not_assume_group() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    _statements, facts, _derived, metrics = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        expected_entity_scope=EntityScope.COMPANY,
        target_period_end=date(1999, 1, 1),
    )
    assert metrics.documents_parsed == 1
    assert facts
    pat = next(fact for fact in facts if fact.metric_code == "PAT")
    assert pat.entity_scope is EntityScope.COMPANY
    assert pat.period_end == date(2026, 6, 30)
    assert pat.source_ref.source_sha256 == document.source_sha256
    assert pat.normalized_value == Decimal("1234000")
    assert pat.publication_status is PublicationStatus.ELIGIBLE


def test_group_is_not_converted_to_company() -> None:
    document = geometric_document(
        (
            ((40.0, "GROUP"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        expected_entity_scope=EntityScope.COMPANY,
    )
    assert not [fact for fact in facts if fact.metric_code == "PAT"]


def test_missing_entity_is_not_filled_with_company() -> None:
    document = geometric_document(
        (
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="issuer-1")
    assert all(fact.metric_code != "PAT" or fact.entity_scope is not None for fact in facts)
    assert not [fact for fact in facts if fact.metric_code == "PAT"]


def test_six_month_flow_is_withheld_not_used_as_q4() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the six months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "5,000")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(document, issuer_id="issuer-1")
    assert facts
    pat = next(fact for fact in facts if fact.metric_code == "PAT")
    assert pat.duration_months == 6
    assert pat.publication_status is PublicationStatus.WITHHELD
    assert "EXACT_QUARTER_NOT_REPORTED" in pat.reason_codes or "CUMULATIVE_ONLY" in pat.reason_codes


def test_q4_or_year_flow_is_blocked() -> None:
    fact = source_fact(duration_months=12)
    validated = validate_source_facts((fact,))
    assert validated[0].validation_status is ValidationStatus.FAILED
    assert validated[0].publication_status is PublicationStatus.WITHHELD
    assert "Q4_OR_CUMULATIVE_FLOW_BLOCKED" in validated[0].reason_codes


def test_liabilities_are_not_derived_from_assets_minus_equity() -> None:
    assets = source_fact(
        metric_code="TOTAL_ASSETS", fact_id="a", cell_id="ca", normalized_value=Decimal("100")
    )
    equity = source_fact(
        metric_code="TOTAL_EQUITY",
        fact_id="e",
        cell_id="ce",
        normalized_value=Decimal("40"),
        raw_value=Decimal("40"),
    )
    derived = derive_facts(validate_source_facts((assets, equity)))
    assert all(item.metric_code != "TOTAL_LIABILITIES" for item in derived)


def test_derived_eps_selected_and_ratios() -> None:
    pat = source_fact(
        metric_code="PAT",
        fact_id="pat",
        cell_id="cpat",
        normalized_value=Decimal("10"),
        raw_value=Decimal("10"),
    )
    basic = source_fact(
        metric_code="EPS_BASIC",
        fact_id="epsb",
        cell_id="ceps",
        unit_dimension=UnitDimension.PER_SHARE,
        normalized_value=Decimal("2"),
        raw_value=Decimal("2"),
        source_scale=Decimal("1"),
    )
    equity = source_fact(
        metric_code="TOTAL_EQUITY",
        fact_id="eq",
        cell_id="ceq",
        normalized_value=Decimal("50"),
        raw_value=Decimal("50"),
    )
    validated = validate_source_facts((pat, basic, equity))
    assert all(item.validation_status is ValidationStatus.PASSED for item in validated)
    derived = derive_facts(validated)
    codes = {item.metric_code for item in derived}
    assert "EPS_SELECTED" in codes
    assert "ROE" in codes
    selected = next(item for item in derived if item.metric_code == "EPS_SELECTED")
    assert selected.normalized_value == Decimal("2")
    assert "cell_id" not in selected.model_dump()


def test_balance_sheet_stocks_do_not_inherit_flow_duration() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "As at 30 June 2026"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Total assets"), (300.0, "10,000")),
        ),
        title="Statement of financial position",
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        expected_entity_scope=EntityScope.COMPANY,
    )
    assets = next(fact for fact in facts if fact.metric_code == "TOTAL_ASSETS")
    assert assets.duration_months is None
    assert assets.source_scale == Decimal("1000")
    assert assets.normalized_value == Decimal("10000000")


def test_eps_does_not_inherit_statement_thousand_scale() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Basic earnings per share"), (300.0, "0.89")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document,
        issuer_id="issuer-1",
        expected_entity_scope=EntityScope.COMPANY,
    )
    eps = next(fact for fact in facts if fact.metric_code == "EPS_BASIC")
    assert eps.duration_months == 3
    assert eps.source_scale == Decimal("1")
    assert eps.normalized_value == Decimal("0.89")
    assert eps.publication_status is PublicationStatus.ELIGIBLE
