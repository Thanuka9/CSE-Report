"""Audit finding 3 — header dates/durations/entities come from the page, never defaults."""

from __future__ import annotations

from datetime import date

from cse_financial_etl.compiler.header_tree import compile_header
from cse_financial_etl.compiler.known_context import build_known_context
from cse_financial_etl.compiler.structure_normalizer import (
    normalize_date,
    normalize_duration_phrase,
)
from cse_financial_etl.document.table_reconstructor import reconstruct_page_tables

from .synthetic_pages import make_page, right_aligned, words

C1_X, C2_X, C3_X, C4_X = 340.0, 420.0, 500.0, 580.0


def _compile(page, *, statement_type="PROFIT_LOSS", known=None):
    tables = reconstruct_page_tables(page)
    assert len(tables) == 1, tables
    return compile_header(tables[0], statement_type=statement_type, known=known)


def _cols(compilation):
    return {c.col_idx: c for c in compilation.columns if c.kind == "VALUE"}


def test_company_three_months_ended_30_june_2026() -> None:
    page = make_page(
        [
            [*words("Company for the three months ended 30 June 2026", 300)],
            [("2026", 318, 340), ("2025", 398, 420)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("90", C2_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("9", C2_X)],
        ]
    )
    cols = _cols(_compile(page))
    current = cols[1]
    assert current.entity == "COMPANY"
    assert current.period_end == date(2026, 6, 30)
    assert current.duration_months == 3
    assert current.period_start == date(2026, 4, 1)
    assert current.comparison_role == "CURRENT"
    comparative = cols[2]
    assert comparative.period_end == date(2025, 6, 30)
    assert comparative.duration_months == 3
    assert comparative.comparison_role == "COMPARATIVE"


def test_mixed_group_company_quarter_ytd_blocks_bind_spatially() -> None:
    # Company | Group parents, each over Quarter + Six months leaf pairs (MBSL layout).
    page = make_page(
        [
            [("Company", 320, 420), ("Group", 480, 580)],
            [*words("Quarter ended", 300), *words("Six months ended", 380), *words("Quarter ended", 460), *words("Six months ended", 540)],
            [("6/30/2026", 300, 340), ("6/30/2026", 380, 420), ("6/30/2026", 460, 500), ("6/30/2026", 540, 580)],
            [("LKR'000", 300, 340), ("LKR'000", 380, 420), ("LKR'000", 460, 500), ("LKR'000", 540, 580)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("200", C2_X), right_aligned("110", C3_X), right_aligned("220", C4_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("20", C2_X), right_aligned("11", C3_X), right_aligned("22", C4_X)],
        ]
    )
    cols = _cols(_compile(page))
    assert [cols[i].entity for i in (1, 2, 3, 4)] == ["COMPANY", "COMPANY", "GROUP", "GROUP"]
    assert [cols[i].duration_months for i in (1, 2, 3, 4)] == [3, 6, 3, 6]
    assert all(cols[i].period_end == date(2026, 6, 30) for i in (1, 2, 3, 4))
    assert all(cols[i].comparison_role == "CURRENT" for i in (1, 2, 3, 4))


def test_missing_entity_stays_none_and_expected_context_only_flags_conflicts() -> None:
    page = make_page(
        [
            [*words("For the three months ended 30 June 2026", 300)],
            [("2026", 318, 340), ("2025", 398, 420)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("90", C2_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("9", C2_X)],
        ]
    )
    known = build_known_context(
        issuer_name="X PLC", symbol="X.N0000", period_end=date(2026, 3, 31), required_entity="COMPANY"
    )
    compilation = _compile(page, known=known)
    cols = _cols(compilation)
    assert cols[1].entity is None  # never defaulted to COMPANY
    assert cols[1].period_end == date(2026, 6, 30)  # observed wins; expected did not overwrite
    assert any("PERIOD_END_MISMATCH" in c for c in compilation.conflicts), compilation.conflicts


def test_known_target_cannot_change_source_comparison_roles() -> None:
    page = make_page(
        [
            [*words("Company for the three months ended 30 June 2026", 300)],
            [("2026", 318, 340), ("2025", 398, 420)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("90", C2_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("9", C2_X)],
        ]
    )
    known_matching = build_known_context(
        issuer_name="X PLC", symbol="X.N0000", period_end=date(2026, 6, 30), required_entity="COMPANY"
    )
    known_different = build_known_context(
        issuer_name="X PLC", symbol="X.N0000", period_end=date(2027, 6, 30), required_entity="COMPANY"
    )
    matching = _cols(_compile(page, known=known_matching))
    different = _cols(_compile(page, known=known_different))
    assert [matching[i].comparison_role for i in (1, 2)] == ["CURRENT", "COMPARATIVE"]
    assert [different[i].comparison_role for i in (1, 2)] == ["CURRENT", "COMPARATIVE"]
    assert matching[1].evidence["comparison_role"]["source"] == "source_header_date_order"
    assert different[1].evidence["comparison_role"]["source"] == "source_header_date_order"


def test_incomplete_sibling_dates_do_not_promote_surviving_date_to_current() -> None:
    page = make_page(
        [
            [*words("Statement of profit or loss", 40)],
            [*words("For the three months ended", 300)],
            [("30.06.2025", 300, 340)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("90", C2_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("9", C2_X)],
        ]
    )
    cols = _cols(_compile(page))
    assert len(cols) == 2
    assert cols[1].period_end == date(2025, 6, 30)
    assert cols[2].period_end is None
    assert cols[1].comparison_role is None
    assert cols[2].comparison_role is None


def test_year_ended_and_as_at_and_bare_year_do_not_become_31_december() -> None:
    assert normalize_date("three months ended 30 June 2026") == date(2026, 6, 30)
    assert normalize_date("year ended 31 March 2026") == date(2026, 3, 31)
    assert normalize_date("as at 30.06.2026") == date(2026, 6, 30)
    assert normalize_date("2026") is None
    assert normalize_duration_phrase("quarter ended") == 3
    assert normalize_duration_phrase("nine months ended") == 9
    assert normalize_duration_phrase("year ended") == 12
    assert normalize_duration_phrase("period ended") is None


def test_financial_position_columns_have_no_duration_and_roles_from_dates() -> None:
    page = make_page(
        [
            words("STATEMENT OF FINANCIAL POSITION", 40),
            [("Group", 320, 420), ("Company", 480, 580)],
            [*words("As at", 40), ("30.06.2026", 290, 340), ("31.12.2025", 370, 420), ("30.06.2026", 450, 500), ("31.12.2025", 530, 580)],
            [*words("Total assets", 40), right_aligned("500", C1_X), right_aligned("450", C2_X), right_aligned("300", C3_X), right_aligned("280", C4_X)],
            [*words("Total equity", 40), right_aligned("300", C1_X), right_aligned("280", C2_X), right_aligned("200", C3_X), right_aligned("190", C4_X)],
        ]
    )
    cols = _cols(_compile(page, statement_type="FINANCIAL_POSITION"))
    assert [cols[i].entity for i in (1, 2, 3, 4)] == ["GROUP", "GROUP", "COMPANY", "COMPANY"]
    assert [cols[i].period_end for i in (1, 2, 3, 4)] == [
        date(2026, 6, 30),
        date(2025, 12, 31),
        date(2026, 6, 30),
        date(2025, 12, 31),
    ]
    assert all(cols[i].duration_months is None for i in (1, 2, 3, 4))
    assert [cols[i].comparison_role for i in (1, 2, 3, 4)] == ["CURRENT", "COMPARATIVE", "CURRENT", "COMPARATIVE"]


def test_single_source_column_role_is_query_invariant() -> None:
    page = make_page(
        [
            [*words("Statement of profit or loss - Company", 40)],
            [*words("For the three months ended 30 June 2026", 300)],
            [("30.06.2026", 300, 340)],
            [*words("Revenue", 40), right_aligned("100", C1_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X)],
        ]
    )
    known_matching = build_known_context(
        issuer_name="X PLC", symbol="X.N0000", period_end=date(2026, 6, 30), required_entity="COMPANY"
    )
    known_other = build_known_context(
        issuer_name="X PLC", symbol="X.N0000", period_end=date(2027, 6, 30), required_entity="COMPANY"
    )
    matching = _cols(_compile(page, known=known_matching))
    other = _cols(_compile(page, known=known_other))
    assert matching[1].period_end == other[1].period_end == date(2026, 6, 30)
    assert matching[1].comparison_role == other[1].comparison_role == "CURRENT"
    assert matching[1].evidence["comparison_role"]["source_owned"] is True
    assert other[1].evidence["comparison_role"]["source_owned"] is True
