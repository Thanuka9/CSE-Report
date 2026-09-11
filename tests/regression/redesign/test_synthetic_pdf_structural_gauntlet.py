"""Structural adversarial PDFs for generalized statement extraction.

These cases exercise layouts that occur across issuers and must never be solved with
symbol-specific rules.  Positive cases require source-owned structure; negative cases
must fail closed rather than borrowing query context or neighbouring values.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.config import load_issuers
from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from tests.regression.redesign.synthetic_pdf_factory import statement_page, write_pdf

ROOT = Path(__file__).resolve().parents[3]
PERIOD_END = date(2026, 6, 30)
ISSUER = "Dialog Axiata PLC"
SYMBOL = "DIAL.N0000"


def _extract(pdf: Path) -> list[ExtractedFact]:
    return extract_filing(
        pdf,
        ISSUER,
        SYMBOL,
        PERIOD_END,
        ocr_enabled=False,
        issuers=load_issuers(ROOT),
    )


def _published(fact: ExtractedFact) -> bool:
    return fact.status in {"EXTRACTED", "EXTRACTED_DERIVED"} and fact.normalized_value is not None


def _one(facts: list[ExtractedFact], code: str) -> ExtractedFact:
    hits = [fact for fact in facts if fact.metric_code == code and _published(fact)]
    assert len(hits) == 1, [(f.status, f.normalized_value, f.source_line) for f in facts if f.metric_code == code]
    return hits[0]


def _none(facts: list[ExtractedFact], code: str) -> None:
    assert not [fact for fact in facts if fact.metric_code == code and _published(fact)]


def test_numeric_note_column_is_not_treated_as_financial_value(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        header_rows=[
            [(285.0, "Note"), (380.0, "30 Jun 2026"), (485.0, "30 Jun 2025")],
        ],
        rows=[
            ("Revenue", [(285.0, "4"), (380.0, "1,000"), (485.0, "900")]),
            ("Operating profit", [(285.0, "7"), (380.0, "250"), (485.0, "180")]),
            ("Profit before tax", [(285.0, "8"), (380.0, "200"), (485.0, "150")]),
            ("Profit for the period", [(285.0, "9"), (380.0, "160"), (485.0, "120")]),
        ],
        extra_bottom_lines=[
            "The first numeric column is a note reference, not a monetary amount",
            "Column ownership must come from the source header hierarchy",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "note_column.pdf", [page]))
    assert _one(facts, "TOP_LINE").normalized_value == Decimal("1000000")
    assert _one(facts, "OPERATING_PROFIT").normalized_value == Decimal("250000")
    assert _one(facts, "PBT").normalized_value == Decimal("200000")
    assert _one(facts, "PAT").normalized_value == Decimal("160000")


def test_percentage_change_column_cannot_become_monetary_fact(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        header_rows=[
            [(360.0, "30 Jun 2026"), (455.0, "30 Jun 2025"), (535.0, "Change %")],
        ],
        rows=[
            ("Revenue", [(360.0, "1,000"), (455.0, "900"), (535.0, "11.1%")]),
            ("Operating profit", [(360.0, "250"), (455.0, "180"), (535.0, "38.9%")]),
            ("Profit before tax", [(360.0, "200"), (455.0, "150"), (535.0, "33.3%")]),
            ("Profit for the period", [(360.0, "160"), (455.0, "120"), (535.0, "33.3%")]),
        ],
        extra_bottom_lines=[
            "The right-most numeric-looking column is a percentage change column",
            "Percentages must never compete with monetary VALUE columns",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "percentage_column.pdf", [page]))
    assert _one(facts, "TOP_LINE").normalized_value == Decimal("1000000")
    assert _one(facts, "OPERATING_PROFIT").normalized_value == Decimal("250000")
    assert _one(facts, "PBT").normalized_value == Decimal("200000")
    assert _one(facts, "PAT").normalized_value == Decimal("160000")


def test_quarter_and_ytd_columns_select_exact_three_month_source_block(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the six months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        header_rows=[
            [(305.0, "Three months ended"), (475.0, "Six months ended")],
            [
                (270.0, "30 Jun 2026"),
                (345.0, "30 Jun 2025"),
                (430.0, "30 Jun 2026"),
                (505.0, "30 Jun 2025"),
            ],
        ],
        rows=[
            ("Revenue", [(270.0, "1,000"), (345.0, "900"), (430.0, "1,900"), (505.0, "1,700")]),
            ("Operating profit", [(270.0, "250"), (345.0, "180"), (430.0, "460"), (505.0, "350")]),
            ("Profit before tax", [(270.0, "200"), (345.0, "150"), (430.0, "370"), (505.0, "290")]),
            ("Profit for the period", [(270.0, "160"), (345.0, "120"), (430.0, "300"), (505.0, "230")]),
        ],
        extra_bottom_lines=[
            "Quarter and cumulative YTD values share the same statement and period end",
            "Exact-quarter facts must be selected from the source-owned three-month block",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "quarter_ytd.pdf", [page]))
    top = _one(facts, "TOP_LINE")
    pat = _one(facts, "PAT")
    assert top.normalized_value == Decimal("1000000")
    assert pat.normalized_value == Decimal("160000")
    assert top.duration_months == pat.duration_months == 3
    assert top.comparison_role == pat.comparison_role == "CURRENT"


def test_repeated_header_can_support_cross_page_continuation(tmp_path: Path) -> None:
    first = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(380.0, "30 Jun 2026"), (485.0, "30 Jun 2025")],
        rows=[
            ("Revenue", [(380.0, "1,000"), (485.0, "900")]),
            ("Operating profit", [(380.0, "250"), (485.0, "180")]),
        ],
    )
    continuation = statement_page(
        title="COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(380.0, "30 Jun 2026"), (485.0, "30 Jun 2025")],
        rows=[
            ("Profit before tax", [(380.0, "200"), (485.0, "150")]),
            ("Profit for the period", [(380.0, "160"), (485.0, "120")]),
        ],
        extra_bottom_lines=["Continued from the preceding statement page"],
    )
    facts = _extract(write_pdf(tmp_path / "evidenced_continuation.pdf", [first, continuation]))
    assert _one(facts, "TOP_LINE").normalized_value == Decimal("1000000")
    assert _one(facts, "PBT").normalized_value == Decimal("200000")
    assert _one(facts, "PAT").normalized_value == Decimal("160000")


def test_unevidenced_numeric_page_cannot_borrow_previous_statement_context(tmp_path: Path) -> None:
    first = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(380.0, "30 Jun 2026"), (485.0, "30 Jun 2025")],
        rows=[
            ("Revenue", [(380.0, "1,000"), (485.0, "900")]),
            ("Operating profit", [(380.0, "250"), (485.0, "180")]),
        ],
    )
    second = statement_page(
        title="",
        period_line="",
        unit_line=None,
        headers=[],
        rows=[
            ("Profit before tax", [(380.0, "200"), (485.0, "150")]),
            ("Profit for the period", [(380.0, "160"), (485.0, "120")]),
        ],
        extra_bottom_lines=[
            "No repeated period entity unit or date header is present on this page",
            "Adjacency alone must never authorize context inheritance",
        ],
    )
    facts = _extract(write_pdf(tmp_path / "unevidenced_continuation.pdf", [first, second]))
    _none(facts, "PBT")
    _none(facts, "PAT")
