from __future__ import annotations

from cse_financial_etl.v2.contracts.enums import MatchKind, StatementType
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
