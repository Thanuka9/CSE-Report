"""Adversarial end-to-end PDF acceptance matrix.

These tests intentionally construct small searchable PDFs that represent recurring CSE
layout and trust-boundary failure modes. They exercise the public ``extract_filing``
entry point; a test must never be made green by bypassing the compiler or weakening a
publication gate.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.config import load_issuers
from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from tests.regression.redesign.synthetic_pdf_factory import statement_page, write_pdf

ROOT = Path(__file__).resolve().parents[3]
PERIOD_END = date(2026, 6, 30)
COMPANY_ISSUER = "Dialog Axiata PLC"
COMPANY_SYMBOL = "DIAL.N0000"
BANK_ISSUER = "Commercial Bank of Ceylon PLC"
BANK_SYMBOL = "COMB.N0000"
CURRENT_X = 380.0
PRIOR_X = 485.0


def _extract(
    pdf: Path,
    *,
    issuer: str = COMPANY_ISSUER,
    symbol: str = COMPANY_SYMBOL,
) -> list[ExtractedFact]:
    return extract_filing(
        pdf,
        issuer,
        symbol,
        PERIOD_END,
        ocr_enabled=False,
        issuers=load_issuers(ROOT),
    )


def _facts(facts: list[ExtractedFact], code: str) -> list[ExtractedFact]:
    return [fact for fact in facts if fact.metric_code == code]


def _published(fact: ExtractedFact) -> bool:
    return fact.status in {"EXTRACTED", "EXTRACTED_DERIVED"} and fact.normalized_value is not None


def _published_fact(facts: list[ExtractedFact], code: str) -> ExtractedFact:
    hits = [fact for fact in _facts(facts, code) if _published(fact)]
    assert len(hits) == 1, [(fact.status, fact.normalized_value) for fact in _facts(facts, code)]
    return hits[0]


def _assert_not_published(facts: list[ExtractedFact], code: str) -> None:
    assert not [fact for fact in _facts(facts, code) if _published(fact)], [
        (fact.status, fact.normalized_value, fact.comparison_role, fact.entity_scope)
        for fact in _facts(facts, code)
    ]


def _standard_pl(*, unit: str | None = "Rs.'000") -> list[tuple[float, float, str]]:
    return statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line=unit,
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Operating profit", [(CURRENT_X, "250"), (PRIOR_X, "180")]),
            ("Profit before tax", [(CURRENT_X, "200"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
            ("Basic earnings per ordinary share", [(CURRENT_X, "1.20"), (PRIOR_X, "0.90")]),
            ("Diluted earnings per ordinary share", [(CURRENT_X, "1.10"), (PRIOR_X, "0.85")]),
        ],
        extra_bottom_lines=[
            "Figures are unaudited and form part of the interim financial statements",
            "Comparative information is presented for the corresponding prior period",
        ],
    )


def _standard_sofp(*, unit: str | None = "Rs.'000") -> list[tuple[float, float, str]]:
    return statement_page(
        title="STATEMENT OF FINANCIAL POSITION - COMPANY",
        period_line="As at 30 June 2026",
        unit_line=unit,
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "31 Mar 2026")],
        rows=[
            ("Total assets", [(CURRENT_X, "5,000"), (PRIOR_X, "4,500")]),
            ("Total liabilities", [(CURRENT_X, "3,000"), (PRIOR_X, "2,700")]),
            ("Total equity", [(CURRENT_X, "2,000"), (PRIOR_X, "1,800")]),
            ("Net assets per share", [(CURRENT_X, "15.00"), (PRIOR_X, "14.00")]),
        ],
        extra_bottom_lines=[
            "The statement should be read together with the accompanying notes",
            "Amounts are presented in Sri Lankan Rupees unless otherwise stated",
        ],
    )


def test_clean_filing_recovers_owned_values_units_periods_and_eps(tmp_path: Path) -> None:
    pdf = write_pdf(tmp_path / "clean_company.pdf", [_standard_pl(), _standard_sofp()])
    facts = _extract(pdf)

    expected = {
        "TOP_LINE": Decimal("1000000"),
        "OPERATING_PROFIT": Decimal("250000"),
        "PBT": Decimal("200000"),
        "PAT": Decimal("160000"),
        "EPS_BASIC": Decimal("1.20"),
        "EPS_DILUTED": Decimal("1.10"),
        "TOTAL_ASSETS": Decimal("5000000"),
        "TOTAL_LIABILITIES": Decimal("3000000"),
        "TOTAL_EQUITY": Decimal("2000000"),
        "NAVPS": Decimal("15.00"),
    }
    for code, value in expected.items():
        fact = _published_fact(facts, code)
        assert fact.normalized_value == value, (code, fact.normalized_value)
        assert fact.period_end == PERIOD_END
        assert fact.entity_scope == "COMPANY"
        assert fact.currency == "LKR"
        evidence = json.loads(fact.evidence_json or "{}")
        assert evidence.get("publication_routing") == "statement_compiler"
        assert evidence.get("explicit_fallback") is None

    for code in ("TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"):
        fact = _published_fact(facts, code)
        assert fact.comparison_role == "CURRENT"
        assert fact.duration_months == 3
        assert fact.scale_factor == 1000

    for code in ("EPS_BASIC", "EPS_DILUTED", "NAVPS"):
        fact = _published_fact(facts, code)
        assert fact.scale_factor == 1, (code, fact.scale_factor)


def test_two_values_without_column_identity_fail_closed(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Operating profit", [(CURRENT_X, "250"), (PRIOR_X, "180")]),
            ("Profit before tax", [(CURRENT_X, "200"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
        extra_bottom_lines=[
            "No current or comparative column header is printed on this synthetic page",
            "The query period must not be injected into an unresolved numeric column",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "ambiguous_columns.pdf", [page]))
    for code in ("TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"):
        _assert_not_published(facts, code)


def test_source_period_mismatch_cannot_inherit_query_period(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2025",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2025"), (PRIOR_X, "30 Jun 2024")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Profit before tax", [(CURRENT_X, "200"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
        extra_bottom_lines=[
            "This page intentionally belongs to a different reporting period",
            "Target-period context is external and must never rewrite source evidence",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "wrong_period.pdf", [page]))
    for code in ("TOP_LINE", "PBT", "PAT"):
        _assert_not_published(facts, code)


def test_missing_monetary_unit_fails_closed(tmp_path: Path) -> None:
    facts = _extract(write_pdf(tmp_path / "missing_unit.pdf", [_standard_pl(unit=None)]))
    for code in ("TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"):
        _assert_not_published(facts, code)


def test_units_are_statement_scoped_not_first_unit_in_filing(tmp_path: Path) -> None:
    sofp_millions = statement_page(
        title="STATEMENT OF FINANCIAL POSITION - COMPANY",
        period_line="As at 30 June 2026",
        unit_line="Rs. Mn",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "31 Mar 2026")],
        rows=[
            ("Total assets", [(CURRENT_X, "5"), (PRIOR_X, "4")]),
            ("Total liabilities", [(CURRENT_X, "3"), (PRIOR_X, "2")]),
            ("Total equity", [(CURRENT_X, "2"), (PRIOR_X, "2")]),
        ],
        extra_bottom_lines=[
            "This statement deliberately uses a different scale from profit or loss",
            "Unit resolution must stay attached to the statement that owns each value",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "mixed_units.pdf", [_standard_pl(), sofp_millions]))
    assert _published_fact(facts, "TOP_LINE").normalized_value == Decimal("1000000")
    assert _published_fact(facts, "TOP_LINE").scale_factor == 1000
    assert _published_fact(facts, "TOTAL_ASSETS").normalized_value == Decimal("5000000")
    assert _published_fact(facts, "TOTAL_ASSETS").scale_factor == 1000000


def test_parenthesised_negative_is_negative_not_positive(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Operating profit", [(CURRENT_X, "(250)"), (PRIOR_X, "180")]),
            ("Profit before tax", [(CURRENT_X, "(200)"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "(160)"), (PRIOR_X, "120")]),
        ],
        extra_bottom_lines=[
            "Parentheses denote losses and must preserve the accounting sign",
            "A formatting parser must not strip the sign during normalization",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "negative_parentheses.pdf", [page]))
    assert _published_fact(facts, "OPERATING_PROFIT").normalized_value == Decimal("-250000")
    assert _published_fact(facts, "PBT").normalized_value == Decimal("-200000")
    assert _published_fact(facts, "PAT").normalized_value == Decimal("-160000")


def test_dash_is_missing_not_numeric_zero(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Profit before tax", [(CURRENT_X, "200"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "-"), (PRIOR_X, "120")]),
        ],
        extra_bottom_lines=[
            "A dash represents an unavailable or nil presentation cell, not an invented zero",
            "The parser must not manufacture a current-period PAT from the comparative cell",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "dash_missing.pdf", [page]))
    pat = _facts(facts, "PAT")
    assert not [fact for fact in pat if fact.normalized_value == Decimal("0") and _published(fact)]
    _assert_not_published(facts, "PAT")


def test_liabilities_and_equity_label_is_not_total_liabilities(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF FINANCIAL POSITION - COMPANY",
        period_line="As at 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "31 Mar 2026")],
        rows=[
            ("Total assets", [(CURRENT_X, "5,000"), (PRIOR_X, "4,500")]),
            ("Total equity", [(CURRENT_X, "2,000"), (PRIOR_X, "1,800")]),
            ("Total liabilities and equity", [(CURRENT_X, "5,000"), (PRIOR_X, "4,500")]),
        ],
        extra_bottom_lines=[
            "The combined balance line is not an explicit total-liabilities disclosure",
            "TOTAL_LIABILITIES is explicit-only and must not be inferred from this label",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "liabilities_and_equity.pdf", [page]))
    assert _published_fact(facts, "TOTAL_ASSETS").normalized_value == Decimal("5000000")
    assert _published_fact(facts, "TOTAL_EQUITY").normalized_value == Decimal("2000000")
    _assert_not_published(facts, "TOTAL_LIABILITIES")


def test_duplicate_conflicting_metric_rows_do_not_last_write_win(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Revenue", [(CURRENT_X, "1,200"), (PRIOR_X, "950")]),
            ("Profit before tax", [(CURRENT_X, "200"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
        extra_bottom_lines=[
            "The duplicate current-period revenue rows intentionally conflict",
            "No dictionary overwrite or first-row shortcut may choose one arbitrarily",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "duplicate_revenue.pdf", [page]))
    _assert_not_published(facts, "TOP_LINE")


def test_bank_sector_aliases_are_bound_to_bank_scope(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - BANK",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Gross income", [(CURRENT_X, "10,000"), (PRIOR_X, "9,000")]),
            (
                "Operating profit before taxes on financial services",
                [(CURRENT_X, "2,500"), (PRIOR_X, "2,100")],
            ),
            ("Profit before tax", [(CURRENT_X, "2,000"), (PRIOR_X, "1,700")]),
            ("Profit for the period", [(CURRENT_X, "1,600"), (PRIOR_X, "1,300")]),
        ],
        extra_bottom_lines=[
            "Bank-specific top-line and operating-profit terminology is deliberate",
            "Sector aliases must not require a general-company Revenue label",
        ],
    )
    facts = _extract(
        write_pdf(tmp_path / "bank_aliases.pdf", [page]),
        issuer=BANK_ISSUER,
        symbol=BANK_SYMBOL,
    )
    top = _published_fact(facts, "TOP_LINE")
    operating = _published_fact(facts, "OPERATING_PROFIT")
    assert top.normalized_value == Decimal("10000000")
    assert operating.normalized_value == Decimal("2500000")
    assert top.entity_scope == "BANK"
    assert operating.entity_scope == "BANK"


def test_prohibited_ebitda_alias_does_not_become_operating_profit(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("EBITDA", [(CURRENT_X, "300"), (PRIOR_X, "250")]),
            ("Profit before tax", [(CURRENT_X, "200"), (PRIOR_X, "150")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
        extra_bottom_lines=[
            "EBITDA is intentionally present as a prohibited operating-profit alias",
            "The semantic layer must not convert a nearby profitability subtotal into EBIT",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "prohibited_ebitda.pdf", [page]))
    _assert_not_published(facts, "OPERATING_PROFIT")


def test_dual_group_company_columns_choose_source_owned_company_current(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        header_rows=[
            [(288.0, "GROUP"), (438.0, "COMPANY")],
            [
                (270.0, "30 Jun 2026"),
                (345.0, "30 Jun 2025"),
                (430.0, "30 Jun 2026"),
                (505.0, "30 Jun 2025"),
            ],
        ],
        rows=[
            (
                "Revenue",
                [(270.0, "2,000"), (345.0, "1,800"), (430.0, "1,000"), (505.0, "900")],
            ),
            (
                "Operating profit",
                [(270.0, "500"), (345.0, "420"), (430.0, "250"), (505.0, "180")],
            ),
            (
                "Profit before tax",
                [(270.0, "400"), (345.0, "350"), (430.0, "200"), (505.0, "150")],
            ),
            (
                "Profit for the period",
                [(270.0, "320"), (345.0, "280"), (430.0, "160"), (505.0, "120")],
            ),
        ],
        extra_bottom_lines=[
            "Both consolidated and standalone columns are printed on the same statement",
            "The target entity must be selected from the header tree, not numeric position alone",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "dual_entity.pdf", [page]))
    assert _published_fact(facts, "TOP_LINE").normalized_value == Decimal("1000000")
    assert _published_fact(facts, "OPERATING_PROFIT").normalized_value == Decimal("250000")
    assert _published_fact(facts, "PAT").normalized_value == Decimal("160000")
    for code in ("TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT"):
        assert _published_fact(facts, code).entity_scope == "COMPANY"


def test_eps_uses_per_share_scale_not_statement_thousands(tmp_path: Path) -> None:
    facts = _extract(write_pdf(tmp_path / "per_share_scale.pdf", [_standard_pl()]))
    basic = _published_fact(facts, "EPS_BASIC")
    diluted = _published_fact(facts, "EPS_DILUTED")
    assert basic.normalized_value == Decimal("1.20")
    assert diluted.normalized_value == Decimal("1.10")
    assert basic.currency == diluted.currency == "LKR"
    assert basic.scale_factor == diluted.scale_factor == 1
