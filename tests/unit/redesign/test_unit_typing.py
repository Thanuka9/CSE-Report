"""Audit finding 4 — unit typing is bounded, owned, and resolved per dimension before normalization."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.compiler.known_context import build_known_context
from cse_financial_etl.compiler.statement_compiler import compile_statements
from cse_financial_etl.compiler.structure_normalizer import (
    normalize_unit_declaration,
    parse_unit_text,
)
from cse_financial_etl.compiler.units import (
    MONETARY,
    PER_SHARE,
    SCOPE_PAGE,
    SCOPE_ROW,
    SCOPE_TABLE,
    UnitDeclaration,
    resolve_unit,
    row_unit_declarations,
)
from cse_financial_etl.document.document_ir import CanonicalDocumentIR, DocumentQuality
from cse_financial_etl.document.region_detector import StatementRegion
from cse_financial_etl.document.table_reconstructor import reconstruct_tables

from .synthetic_pages import make_page, right_aligned, words

C1_X, C2_X = 340.0, 420.0


def test_currency_tokens_are_word_bounded() -> None:
    assert parse_unit_text("Equity attributable to Shareholders").currency is None
    assert parse_unit_text("Rs.'000").currency == "LKR"
    assert parse_unit_text("LKR '000").scale == Decimal("1000")
    assert normalize_unit_declaration("Shareholders of the parent") == (None, None)


def test_usd_mn_gives_currency_and_scale_together() -> None:
    parsed = parse_unit_text("USD Mn")
    assert parsed.currency == "USD"
    assert parsed.scale == Decimal("1000000")
    assert parsed.scale_explicit


def test_row_level_per_share_declaration_is_independent_of_table_scale() -> None:
    row = row_unit_declarations("Basic earnings per share (Rs.)", owner="row:1", page=1)
    assert row and row[0].scope == SCOPE_ROW and row[0].currency == "LKR"
    table = [UnitDeclaration.from_text("Rs.'000", scope=SCOPE_TABLE, owner="hdr", page=1)]
    per_share = resolve_unit(PER_SHARE, row=row, column=[], table=table, page=[])
    assert per_share.resolved and per_share.scale == Decimal("1")
    monetary = resolve_unit(MONETARY, row=[], column=[], table=table, page=[])
    assert monetary.resolved and monetary.scale == Decimal("1000") and monetary.scale_owner == "hdr"


def test_conflicting_declarations_in_one_scope_stay_unresolved() -> None:
    table = [
        UnitDeclaration.from_text("Rs.'000", scope=SCOPE_TABLE, owner="hdr-a", page=1),
        UnitDeclaration.from_text("Rs. Mn", scope=SCOPE_TABLE, owner="hdr-b", page=1),
    ]
    res = resolve_unit(MONETARY, row=[], column=[], table=table, page=[])
    assert not res.resolved
    assert any(r.startswith("SCALE_CONFLICT") for r in res.reasons)
    assert res.scale is None


def test_missing_declaration_is_unresolved_not_defaulted() -> None:
    res = resolve_unit(MONETARY, row=[], column=[], table=[], page=[])
    assert not res.resolved
    assert "CURRENCY_MISSING" in res.reasons and "SCALE_MISSING" in res.reasons


def test_page_footnote_thousands_owns_the_scale() -> None:
    page = [
        UnitDeclaration.from_text(
            "Note : All values are in Rs '000s, unless otherwise stated.",
            scope=SCOPE_PAGE,
            owner="page:17:l0",
            page=17,
        )
    ]
    res = resolve_unit(MONETARY, row=[], column=[], table=[], page=page)
    assert res.resolved and res.scale == Decimal("1000") and res.currency == "LKR"
    assert res.scale_owner == "page:17:l0"


def _compile_page(page, statement_type="PROFIT_LOSS"):
    doc = CanonicalDocumentIR(
        pages=(page,),
        quality=DocumentQuality(1, len(page.tokens), 10, 1.0, "synthetic", False),
        source_sha256="deadbeef",
        source_path="synthetic.pdf",
    )
    doc = reconstruct_tables(doc)
    known = build_known_context(
        issuer_name="X PLC",
        symbol="X.N0000",
        period_end=date(2026, 6, 30),
        required_entity="COMPANY",
    )
    region = StatementRegion(
        statement_type=statement_type, page_start=1, page_end=1, confidence=1.0, evidence={}
    )
    return compile_statements(doc, [region], known)


def _row(statement, label_prefix):
    return next(r for r in statement.rows if r.raw_label.lower().startswith(label_prefix))


def test_eps_in_rupees_inside_thousands_table_is_not_scaled() -> None:
    page = make_page(
        [
            words("COMPANY INCOME STATEMENT", 40),
            [*words("Company for the quarter ended 30 June 2026", 300)],
            [("2026", 318, 340), ("2025", 398, 420)],
            [("Rs.'000", 300, 340), ("Rs.'000", 380, 420)],
            [
                *words("Revenue", 40),
                right_aligned("37,231,246", C1_X),
                right_aligned("30,000,000", C2_X),
            ],
            [
                *words("Profit for the period", 40),
                right_aligned("8,187,022", C1_X),
                right_aligned("6,000,000", C2_X),
            ],
            [
                *words("Earnings per share (Rs.)", 40),
                right_aligned("0.89", C1_X),
                right_aligned("0.65", C2_X),
            ],
        ]
    )
    statements = _compile_page(page)
    assert len(statements) == 1
    statement = statements[0]
    pat = _row(statement, "profit for the period")
    eps = _row(statement, "earnings per share")
    assert pat.cells["c1"].value_for(MONETARY) == Decimal("8187022000")
    assert eps.cells["c1"].value_for(PER_SHARE) == Decimal("0.89")
    # The monetary reading of the EPS row would be wrong; the dimension is per-share.
    assert eps.dimension_hint == PER_SHARE
    assert eps.cells["c1"].unit_for(PER_SHARE)["scale"] == "1"
    assert eps.cells["c1"].unit_for(PER_SHARE)["currency"] == "LKR"


def test_mixed_unit_table_keeps_each_column_scale_separate() -> None:
    page = make_page(
        [
            [*words("Company for the quarter ended 30 June 2026", 300)],
            [("2026", 318, 340), ("2025", 398, 420)],
            [("Rs.'000", 300, 340), ("USD Mn", 380, 420)],
            [*words("Revenue", 40), right_aligned("1,000", C1_X), right_aligned("2", C2_X)],
            [
                *words("Profit for the period", 40),
                right_aligned("100", C1_X),
                right_aligned("1", C2_X),
            ],
        ]
    )
    statement = _compile_page(page)[0]
    pat = _row(statement, "profit for the period")
    assert pat.cells["c1"].value_for(MONETARY) == Decimal("100000")
    assert pat.cells["c1"].unit_for(MONETARY)["currency"] == "LKR"
    assert pat.cells["c2"].value_for(MONETARY) == Decimal("1000000")
    assert pat.cells["c2"].unit_for(MONETARY)["currency"] == "USD"


def test_table_without_any_unit_declaration_has_unresolved_cells() -> None:
    page = make_page(
        [
            [*words("Company for the quarter ended 30 June 2026", 300)],
            [("2026", 318, 340), ("2025", 398, 420)],
            [*words("Revenue", 40), right_aligned("1,000", C1_X), right_aligned("900", C2_X)],
            [
                *words("Profit for the period", 40),
                right_aligned("100", C1_X),
                right_aligned("90", C2_X),
            ],
        ]
    )
    statement = _compile_page(page)[0]
    pat = _row(statement, "profit for the period")
    assert pat.cells["c1"].value_for(MONETARY) is None
    assert pat.cells["c1"].unit_for(MONETARY)["status"] == "UNRESOLVED"


def test_rs_dot_000_is_explicit_thousands() -> None:
    from decimal import Decimal

    from cse_financial_etl.compiler.structure_normalizer import parse_unit_text

    parsed = parse_unit_text("Rs.000")
    assert parsed.currency == "LKR"
    assert parsed.scale == Decimal("1000")
    assert parsed.scale_explicit is True
