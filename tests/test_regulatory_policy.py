from datetime import date

from cse_financial_etl.governance.regulatory_policy import (
    canonical_issuer_id,
    expected_disclosure,
    insurance_accounting_regime,
    price_semantic_from_row,
    q4_publication_allowed,
    quarantine_matches,
)


def test_main_and_empower_disclosure_expectations() -> None:
    assert expected_disclosure("MAIN", 1).statement_requirement == "FULL_INTERIM_REQUIRED"
    assert expected_disclosure("MAIN", 4).due_days == 60
    assert expected_disclosure("EMPOWER", 1).statement_requirement == "SUPPLEMENTARY_ONLY"
    assert expected_disclosure("EMPOWER", 2).statement_requirement == "FULL_INTERIM_REQUIRED"


def test_canonical_issuer_id_is_stable_and_config_wins() -> None:
    assert canonical_issuer_id("Example PLC") == canonical_issuer_id("EXAMPLE   PLC")
    assert canonical_issuer_id("Example PLC", "EXAMPLE") == "EXAMPLE"


def test_insurance_regime_does_not_guess_2026_transition() -> None:
    assert insurance_accounting_regime(date(2025, 12, 31)) == "SLFRS4_LEGACY"
    assert insurance_accounting_regime(date(2026, 6, 30)) == "INSURANCE_REGIME_UNRESOLVED"
    assert insurance_accounting_regime(date(2026, 6, 30), explicit_regime="SLFRS4_SOAT") == "SLFRS4_SOAT"


def test_price_semantics_reject_closing_price_only_row() -> None:
    assert price_semantic_from_row({"closing_price": "125.00"}) is None
    assert price_semantic_from_row({"last_traded_price": "123.50", "closing_price": "125"}) == (
        "last_traded_price",
        "123.50",
    )


def test_q4_requires_explicit_three_month_fact() -> None:
    assert q4_publication_allowed(duration_months=3, explicit_quarter=True)
    assert not q4_publication_allowed(duration_months=12, explicit_quarter=False)
    assert not q4_publication_allowed(duration_months=3, explicit_quarter=False)


def test_quarantine_requires_immutable_identity_when_runtime_supplies_it() -> None:
    configured = {
        "issuer_name": "Example PLC",
        "symbol": "EX.N0000",
        "period_end": "2026-06-30",
        "filing_id": 123,
        "sha256": "abc123",
    }
    assert quarantine_matches(
        configured,
        issuer_name="Example PLC",
        symbol="EX.N0000",
        period_end="2026-06-30",
        filing_id=123,
        sha256="abc123",
    )
    assert not quarantine_matches(
        configured,
        issuer_name="Example PLC",
        symbol="EX.N0000",
        period_end="2026-06-30",
        filing_id=124,
        sha256="abc123",
    )
    assert not quarantine_matches(
        configured,
        issuer_name="Example PLC",
        symbol="EX.N0000",
        period_end="2026-06-30",
        filing_id=123,
        sha256="different",
    )
