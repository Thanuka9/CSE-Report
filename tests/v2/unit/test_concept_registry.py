from __future__ import annotations

import pytest

from cse_financial_etl.v2.contracts.enums import MatchKind, StatementType
from cse_financial_etl.v2.contracts.statement import StatementRow
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher
from cse_financial_etl.v2.taxonomy.registry import (
    ConceptDefinition,
    ConceptRegistry,
    RegistryConflictError,
    load_registry,
)


def test_registry_loads_and_rejects_duplicate_aliases() -> None:
    registry = load_registry()
    assert registry.get("PAT").source_only is True
    assert registry.get("TOTAL_LIABILITIES").derivation_allowed is False
    assert registry.lookup_alias("Profit for the period") is registry.get("PAT")
    assert registry.lookup_alias(
        "Operating profit before taxes on financial services"
    ) is registry.get("OPERATING_PROFIT")
    assert registry.lookup_alias("Net book value per share") is registry.get("NAVPS")
    assert registry.lookup_alias(
        "Profit after Tax from continued operations for the period"
    ) is registry.get("PAT")
    assert registry.lookup_alias("Basic earnings/(loss) per share") is registry.get("EPS_BASIC")
    assert registry.lookup_alias("Basic earnings/(loss) per share (Rs.)") is registry.get(
        "EPS_BASIC"
    )
    assert registry.lookup_alias("Net book value per share (LKR)") is registry.get("NAVPS")
    assert registry.lookup_alias("Net Asset Per Share in LKR") is registry.get("NAVPS")
    assert registry.lookup_alias("Earning Per Share (Note-8.6)") is registry.get("EPS_BASIC")
    assert registry.lookup_alias(
        "Earnings Per Share (basic and diluted) in LKR"
    ) is registry.get("EPS_BASIC")
    assert registry.lookup_alias("Basic/diluted earnings per share") is registry.get("EPS_BASIC")
    assert registry.lookup_alias("Basic and diluted earnings per share") is registry.get(
        "EPS_BASIC"
    )
    assert registry.lookup_alias("Earnings per share - basic") is registry.get("EPS_BASIC")
    assert registry.lookup_alias("Earnings per share - diluted") is registry.get("EPS_DILUTED")
    assert registry.lookup_alias("Basic/Diluted (Rs.)") is None
    assert registry.lookup_alias("Gross income") is None
    assert registry.lookup_alias("Gross income", regimes=("BANK",)) is registry.get("TOP_LINE")
    assert registry.lookup_alias("Insurance revenue") is None
    assert registry.lookup_alias("Insurance revenue", regimes=("SLFRS17",)) is registry.get(
        "TOP_LINE"
    )
    assert registry.lookup_alias("Net Profit for the Period ,") is registry.get("PAT")
    assert registry.lookup_alias("Revenue ||") is registry.get("TOP_LINE")
    assert registry.lookup_alias("Profit before Income Tax Expense") is registry.get("PBT")
    assert registry.lookup_alias("Net Profit/(Loss) before Taxation") is registry.get("PBT")
    assert registry.lookup_alias("Total Shareholders' Funds") is registry.get("TOTAL_EQUITY")
    assert registry.lookup_alias(
        "Operating profit/ (loss) before VAT on financial services & SSCL"
    ) is registry.get("OPERATING_PROFIT")
    assert registry.lookup_alias(
        "Profit before Social Security Contribution Levy / Value Added Tax on financial services"
    ) is registry.get("OPERATING_PROFIT")
    assert registry.lookup_alias("Earning per Share (LKR) - For the Period") is registry.get(
        "EPS_BASIC"
    )
    assert registry.lookup_alias(
        "Basic / diluted earnings per share to equity holders"
    ) is registry.get("EPS_BASIC")
    assert registry.lookup_alias("Net Assets Value Per Share") is registry.get("NAVPS")
    assert registry.lookup_alias("Profit for the year") is registry.get("PAT")
    assert registry.lookup_alias("Loss for the year") is registry.get("PAT")
    assert registry.lookup_alias("Basic Loss Per Share") is registry.get("EPS_BASIC")
    assert registry.lookup_alias("Net Asset Value per Share LKR") is registry.get("NAVPS")
    assert registry.lookup_alias("Profit before taxation (184.4%)") is registry.get("PBT")
    assert registry.lookup_alias("Profit after taxation (227.8%)") is registry.get("PAT")
    assert registry.lookup_alias("Restated Basic Earning per Share (LKR)") is registry.get(
        "EPS_BASIC"
    )
    duplicate = registry.concepts[0]
    with pytest.raises(RegistryConflictError):
        ConceptRegistry(
            (
                duplicate,
                ConceptDefinition(
                    code="OTHERPAT",
                    display_name="Other",
                    metric_type="MONETARY_ABSOLUTE",
                    statement_types=duplicate.statement_types,
                    period_behavior=duplicate.period_behavior,
                    unit_dimension=duplicate.unit_dimension,
                    exact_aliases=("Profit for the period",),
                ),
            )
        )


def test_matcher_exact_and_abstains_on_ambiguity() -> None:
    matcher = RegistryMatcher()
    row = StatementRow(
        row_id="r1", raw_label="Profit for the period", normalized_label="profit for the period"
    )
    hits = matcher.candidates(row, statement_type=StatementType.INCOME_STATEMENT)
    assert hits[0].metric_code == "PAT"
    assert hits[0].match_kind is MatchKind.EXACT_ALIAS
    ebitda = StatementRow(row_id="r2", raw_label="EBITDA", normalized_label="ebitda")
    blocked = matcher.candidates(ebitda, statement_type=StatementType.INCOME_STATEMENT)
    assert blocked[0].match_kind is MatchKind.ABSTAIN
    bank_op = StatementRow(
        row_id="r3",
        raw_label="Operating profit before taxes on financial services",
        normalized_label="operating profit before taxes on financial services",
    )
    op_hits = matcher.candidates(bank_op, statement_type=StatementType.INCOME_STATEMENT)
    assert op_hits[0].metric_code == "OPERATING_PROFIT"
    wrong_statement = matcher.candidates(row, statement_type=StatementType.BALANCE_SHEET)
    assert wrong_statement[0].match_kind is MatchKind.ABSTAIN
