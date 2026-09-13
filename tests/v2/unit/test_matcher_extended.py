from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import (
    MatchKind,
    PeriodBehavior,
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
    hits = matcher.candidates(_row("Gross income"), statement_type=StatementType.INCOME_STATEMENT)
    assert hits[0].metric_code == "TOP_LINE"
    assert hits[0].match_kind is MatchKind.EXACT_ALIAS
    interest = matcher.candidates(
        _row("Interest income"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert interest[0].metric_code == "TOP_LINE"
    assert interest[0].match_kind is MatchKind.EXACT_ALIAS


def test_finance_income_row_is_top_line_not_income_tax() -> None:
    matcher = RegistryMatcher()
    income = matcher.candidates(_row("Income"), statement_type=StatementType.INCOME_STATEMENT)
    assert income[0].metric_code == "TOP_LINE"
    assert income[0].match_kind is MatchKind.EXACT_ALIAS
    tax = matcher.candidates(
        _row("Income tax expense"), statement_type=StatementType.INCOME_STATEMENT
    )
    assert tax[0].metric_code != "TOP_LINE"


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
