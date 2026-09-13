from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import (
    AccountingRegime,
    MatchKind,
    PeriodBehavior,
    ResolutionStatus,
    StatementType,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.statement import StatementRow
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher
from cse_financial_etl.v2.taxonomy.registry import ConceptDefinition, ConceptRegistry


def _row(label: str, normalized: str = "") -> StatementRow:
    return StatementRow(row_id="r1", raw_label=label, normalized_label=normalized)


def test_controlled_alias_uses_normalized_label() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("PAT (note 5)", "profit for the period"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code == "PAT"
    assert hits[0].match_kind is MatchKind.CONTROLLED_ALIAS


def test_regime_alias_gross_income_is_top_line() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("Gross income"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.BANK,
    )
    assert hits[0].metric_code == "TOP_LINE"
    assert hits[0].match_kind is MatchKind.EXACT_ALIAS
    interest = matcher.candidates(
        _row("Interest income"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.BANK,
    )
    assert interest[0].metric_code == "TOP_LINE"
    assert interest[0].match_kind is MatchKind.EXACT_ALIAS
    general = matcher.candidates(
        _row("Interest income"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert general[0].metric_code is None
    assert general[0].match_kind is MatchKind.ABSTAIN


def test_insurance_aliases_are_regime_locked() -> None:
    matcher = RegistryMatcher()
    slfrs17 = matcher.candidates(
        _row("Insurance revenue"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.SLFRS17,
    )
    assert slfrs17[0].metric_code == "TOP_LINE"
    assert slfrs17[0].source_concept == "Insurance revenue"
    assert slfrs17[0].matched_alias == "Insurance revenue"
    assert slfrs17[0].accounting_regime is AccountingRegime.SLFRS17
    assert slfrs17[0].accounting_regime_status is ResolutionStatus.RESOLVED
    general = matcher.candidates(
        _row("Insurance revenue"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert general[0].metric_code is None
    gwp = matcher.candidates(
        _row("Gross written premium"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.SLFRS4,
    )
    assert gwp[0].metric_code == "TOP_LINE"
    assert gwp[0].source_concept == "Gross written premium"
    assert gwp[0].matched_alias == "Gross written premium"
    assert gwp[0].accounting_regime is AccountingRegime.SLFRS4
    assert gwp[0].accounting_regime_status is ResolutionStatus.RESOLVED
    nep = matcher.candidates(
        _row("Net earned premium"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.SLFRS4,
    )
    assert nep[0].metric_code == "TOP_LINE"
    slfrs17_gwp = matcher.candidates(
        _row("Gross written premium"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.SLFRS17,
    )
    assert slfrs17_gwp[0].metric_code is None
    generic_insurance = matcher.candidates(
        _row("Insurance revenue"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.INSURANCE,
    )
    assert generic_insurance[0].metric_code == "TOP_LINE"
    assert generic_insurance[0].source_concept == "Insurance revenue"
    assert generic_insurance[0].matched_alias == "Insurance revenue"
    assert generic_insurance[0].accounting_regime is None
    assert generic_insurance[0].accounting_regime is not AccountingRegime.SLFRS4
    assert generic_insurance[0].accounting_regime is not AccountingRegime.SLFRS17
    assert generic_insurance[0].accounting_regime_status is ResolutionStatus.UNRESOLVED


def test_finance_income_row_is_top_line_not_income_tax() -> None:
    matcher = RegistryMatcher()
    income = matcher.candidates(
        _row("Income"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.FINANCE_COMPANY,
    )
    assert income[0].metric_code == "TOP_LINE"
    assert income[0].match_kind is MatchKind.EXACT_ALIAS
    general_income = matcher.candidates(
        _row("Income"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert general_income[0].metric_code is None
    tax = matcher.candidates(
        _row("Income tax expense"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert tax[0].metric_code != "TOP_LINE"


def test_total_operating_income_is_top_line_not_operating_profit() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("Total operating income"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.BANK,
    )
    assert hits[0].metric_code == "TOP_LINE"
    for label in ("Gross income", "Interest income", "Total operating income"):
        finance = matcher.candidates(
            _row(label),
            statement_type=StatementType.INCOME_STATEMENT,
            accounting_regime=AccountingRegime.FINANCE_COMPANY,
        )
        assert finance[0].metric_code == "TOP_LINE", label
    income_tax = matcher.candidates(
        _row("Income tax expense"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.FINANCE_COMPANY,
    )
    assert income_tax[0].metric_code != "TOP_LINE"
    nii = matcher.candidates(
        _row("Net interest income"),
        statement_type=StatementType.INCOME_STATEMENT,
        accounting_regime=AccountingRegime.FINANCE_COMPANY,
    )
    assert nii[0].metric_code != "TOP_LINE"
    digits = matcher.candidates(_row("1,234"), statement_type=StatementType.INCOME_STATEMENT)
    assert digits[0].metric_code is None
    assert digits[0].match_kind is MatchKind.ABSTAIN


def test_revenue_from_contracts_and_slash_pat_aliases() -> None:
    matcher = RegistryMatcher()
    revenue = matcher.candidates(
        _row("Revenue from contracts with customers"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert revenue[0].metric_code == "TOP_LINE"
    pat = matcher.candidates(
        _row("Profit / (loss) for the Period"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert pat[0].metric_code == "PAT"


def test_fuzzy_near_miss_still_maps_pat() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("Profit for the periode"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code == "PAT"
    assert hits[0].match_kind is MatchKind.FUZZY


def test_diluted_only_row_is_not_basic_eps() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("Earnings per share diluted"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert hits[0].metric_code == "EPS_DILUTED"
    discontinued = matcher.candidates(
        _row("Earnings per share from discontinued operations Basic (Rs.)"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert discontinued[0].match_kind is MatchKind.ABSTAIN


def test_closing_market_price_is_not_last_traded() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("Closing market price"),
        statement_type=StatementType.OTHER_FINANCIAL_STATEMENT,
    )
    assert hits[0].metric_code is None
    assert hits[0].match_kind is MatchKind.ABSTAIN


def test_loss_for_the_period_is_pat() -> None:
    matcher = RegistryMatcher()
    hits = matcher.candidates(
        _row("Loss for the period"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert hits[0].metric_code == "PAT"
    op = matcher.candidates(
        _row("Profit from Operation"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert op[0].metric_code == "OPERATING_PROFIT"
    signed = matcher.candidates(
        _row("Profit/(loss) from operations"),
        statement_type=StatementType.INCOME_STATEMENT,
    )
    assert signed[0].metric_code == "OPERATING_PROFIT"
    matcher = RegistryMatcher()
    for label in (
        "Less: Taxes on financial services",
        "Taxes on financial services",
        "VAT on financial services",
    ):
        hits = matcher.candidates(_row(label), statement_type=StatementType.INCOME_STATEMENT)
        assert hits[0].metric_code != "OPERATING_PROFIT", label


def test_ambiguous_fuzzy_candidates_abstain() -> None:
    registry = ConceptRegistry(
        (
            ConceptDefinition(
                code="ALPHA_LINE",
                display_name="Alpha",
                metric_type="MONETARY_ABSOLUTE",
                statement_types=(StatementType.INCOME_STATEMENT,),
                period_behavior=PeriodBehavior.FLOW,
                unit_dimension=UnitDimension.MONETARY,
                exact_aliases=("Alpha income line",),
            ),
            ConceptDefinition(
                code="BETA_LINE",
                display_name="Beta",
                metric_type="MONETARY_ABSOLUTE",
                statement_types=(StatementType.INCOME_STATEMENT,),
                period_behavior=PeriodBehavior.FLOW,
                unit_dimension=UnitDimension.MONETARY,
                exact_aliases=("Beta income line",),
            ),
        )
    )
    matcher = RegistryMatcher(registry)
    hits = matcher.candidates(_row("income line"), statement_type=StatementType.INCOME_STATEMENT)
    kinds = {item.match_kind for item in hits}
    assert MatchKind.ABSTAIN in kinds
    assert {item.metric_code for item in hits if item.metric_code} == {"ALPHA_LINE", "BETA_LINE"}
