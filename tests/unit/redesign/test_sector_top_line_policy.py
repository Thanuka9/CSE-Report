from __future__ import annotations

from cse_financial_etl.tunnels.common_financial_engine import _top_line_allowed


def test_general_corporate_rejects_bank_and_insurance_top_lines() -> None:
    assert _top_line_allowed("REVENUE", "GENERAL_CORPORATE")
    assert _top_line_allowed("TOP_LINE", "GENERAL_CORPORATE")
    assert not _top_line_allowed("GROSS_INCOME", "GENERAL_CORPORATE")
    assert not _top_line_allowed("INSURANCE_REVENUE", "GENERAL_CORPORATE")
    assert not _top_line_allowed("INTEREST_INCOME", "GENERAL_CORPORATE")


def test_bank_uses_governed_bank_top_line_family() -> None:
    assert _top_line_allowed("GROSS_INCOME", "BANK")
    assert _top_line_allowed("NET_INTEREST_INCOME", "BANK")
    assert _top_line_allowed("TOP_LINE", "BANK")
    assert not _top_line_allowed("REVENUE", "BANK")
    assert not _top_line_allowed("INTEREST_INCOME", "BANK")


def test_finance_company_uses_interest_income_basis() -> None:
    assert _top_line_allowed("INTEREST_INCOME", "FINANCE_LEASING")
    assert _top_line_allowed("GROSS_INCOME", "FINANCE_LEASING")
    assert not _top_line_allowed("REVENUE", "FINANCE_LEASING")


def test_insurance_prefers_insurance_revenue_family() -> None:
    assert _top_line_allowed("INSURANCE_REVENUE", "INSURANCE")
    assert _top_line_allowed("GROSS_INCOME", "INSURANCE")
    assert not _top_line_allowed("REVENUE", "INSURANCE")


def test_unknown_profile_fails_closed_to_other_policy() -> None:
    assert _top_line_allowed("TOP_LINE", "UNKNOWN_PROFILE")
    assert not _top_line_allowed("REVENUE", "UNKNOWN_PROFILE")
    assert not _top_line_allowed("GROSS_INCOME", "UNKNOWN_PROFILE")


def test_non_top_line_concepts_are_unaffected() -> None:
    assert _top_line_allowed("PAT", "BANK")
    assert _top_line_allowed("TOTAL_ASSETS", "INSURANCE")
