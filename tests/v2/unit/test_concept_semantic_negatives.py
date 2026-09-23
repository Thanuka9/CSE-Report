from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import AccountingRegime, MatchKind, StatementType
from cse_financial_etl.v2.contracts.statement import StatementRow
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher


def test_ebitda_is_not_operating_profit() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="EBITDA"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code is None
    assert hits[0].match_kind is MatchKind.ABSTAIN


def test_attributable_to_owners_is_not_silently_pat() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Profit attributable to owners of the parent"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code is None


def test_pat_pbt_revenue_positives_match() -> None:
    matcher = RegistryMatcher()
    pat = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Profit for the period"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    pbt = matcher.candidates(
        StatementRow(row_id="r2", raw_label="Profit before tax"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    revenue = matcher.candidates(
        StatementRow(row_id="r3", raw_label="Revenue"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert pat[0].metric_code == "PAT"
    assert pbt[0].metric_code == "PBT"
    assert revenue[0].metric_code == "TOP_LINE"


def test_interest_income_is_bank_top_line_not_general() -> None:
    matcher = RegistryMatcher()
    general = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Interest income"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    bank = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Interest income"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.BANK,
    )
    assert general[0].metric_code is None
    assert bank[0].metric_code == "TOP_LINE"


def test_operating_profit_after_taxes_on_financial_services_is_forbidden() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Operating profit after taxes on financial services"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code is None
    assert hits[0].match_kind is MatchKind.ABSTAIN


def test_closing_market_price_is_not_last_traded_price() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Closing market price"),
        statement_type=StatementType.EPS_NOTE,
    )
    assert hits[0].metric_code is None


def test_narrative_operating_income_is_not_top_line() -> None:
    matcher = RegistryMatcher()
    label = "The Bank's total operating income was recorded as LKR Mn, an increase of"
    sofp = matcher.candidates(
        StatementRow(row_id="r1", raw_label=label),
        statement_type=StatementType.BALANCE_SHEET,
        accounting_regime=AccountingRegime.BANK,
    )
    income = matcher.candidates(
        StatementRow(row_id="r1", raw_label=label),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.BANK,
    )
    assert sofp[0].metric_code is None
    assert income[0].metric_code is None


def test_gross_written_contribution_is_insurance_top_line() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Gross written contribution (premium)"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code == "TOP_LINE"


def test_attributable_equity_is_not_total_equity() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        StatementRow(row_id="r1", raw_label="Equity attributable to owners of the parent"),
        statement_type=StatementType.BALANCE_SHEET,
    )
    assert hits[0].metric_code is None
