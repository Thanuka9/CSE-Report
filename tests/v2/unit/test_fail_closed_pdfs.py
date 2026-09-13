"""Fail-closed PDF gates that production V2 must honor.

These cases are the trust-boundary tests V1 already passed. V2 is the default
extractor, so unlabeled columns, missing units, dashes, conflicts, note columns,
and ambiguous continuation must withhold rather than invent context.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import PublicationStatus
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
from tests.regression.redesign.synthetic_pdf_factory import statement_page, write_pdf

PERIOD_END = date(2026, 6, 30)
CURRENT_X = 380.0
PRIOR_X = 485.0


def _published(facts, code: str):
    return [
        fact
        for fact in facts
        if fact.metric_code == code and fact.publication_status is PublicationStatus.ELIGIBLE
    ]


def _run(pdf: Path):
    return run_pdf_pipeline(pdf, issuer_id="DIAL.N0000", filing_version_id="fail-closed")


def test_two_values_without_column_identity_fail_closed(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
    )
    _statements, facts, _derived, _metrics = _run(write_pdf(tmp_path / "ambiguous.pdf", [page]))
    assert _published(facts, "TOP_LINE") == []
    assert _published(facts, "PAT") == []


def test_missing_monetary_unit_fails_closed(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line=None,
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
            ("Basic earnings per ordinary share", [(CURRENT_X, "1.20"), (PRIOR_X, "0.90")]),
        ],
    )
    _statements, facts, _derived, _metrics = _run(write_pdf(tmp_path / "nounit.pdf", [page]))
    assert _published(facts, "TOP_LINE") == []
    assert _published(facts, "PAT") == []


def test_dash_is_missing_not_numeric_zero(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Profit for the period", [(CURRENT_X, "-"), (PRIOR_X, "120")]),
        ],
    )
    _statements, facts, _derived, _metrics = _run(write_pdf(tmp_path / "dash.pdf", [page]))
    assert not [
        fact for fact in _published(facts, "PAT") if fact.normalized_value == Decimal("0")
    ]
    assert _published(facts, "PAT") == []


def test_duplicate_conflicting_metric_rows_are_withheld(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Revenue", [(CURRENT_X, "1,200"), (PRIOR_X, "950")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
    )
    _statements, facts, _derived, _metrics = _run(write_pdf(tmp_path / "dup.pdf", [page]))
    assert _published(facts, "TOP_LINE") == []
    assert _published(facts, "PAT")[0].normalized_value == Decimal("160000")


def test_numeric_note_column_is_not_a_financial_value(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[],
        header_rows=[[(285.0, "Note"), (380.0, "30 Jun 2026"), (485.0, "30 Jun 2025")]],
        rows=[
            ("Revenue", [(285.0, "4"), (380.0, "1,000"), (485.0, "900")]),
            ("Profit for the period", [(285.0, "9"), (380.0, "160"), (485.0, "120")]),
        ],
    )
    _statements, facts, _derived, _metrics = _run(write_pdf(tmp_path / "note.pdf", [page]))
    top = _published(facts, "TOP_LINE")
    pat = _published(facts, "PAT")
    assert len(top) == 1 and top[0].normalized_value == Decimal("1000000")
    assert len(pat) == 1 and pat[0].normalized_value == Decimal("160000")


def test_ambiguous_continuation_entity_is_not_collapsed(tmp_path: Path) -> None:
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
        title="GROUP COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(380.0, "30 Jun 2026"), (485.0, "30 Jun 2025")],
        rows=[
            ("Profit before tax", [(380.0, "200"), (485.0, "150")]),
            ("Profit for the period", [(380.0, "160"), (485.0, "120")]),
        ],
        extra_bottom_lines=["Continued from the preceding statement page"],
    )
    _statements, facts, _derived, _metrics = _run(
        write_pdf(tmp_path / "ambig_cont.pdf", [first, continuation])
    )
    assert _published(facts, "PBT") == []
    assert _published(facts, "PAT") == []
    assert _published(facts, "TOP_LINE")[0].normalized_value == Decimal("1000000")


def test_headed_current_column_still_publishes(tmp_path: Path) -> None:
    page = statement_page(
        title="STATEMENT OF PROFIT OR LOSS - COMPANY",
        period_line="For the three months ended 30 June 2026",
        unit_line="Rs.'000",
        headers=[(CURRENT_X, "30 Jun 2026"), (PRIOR_X, "30 Jun 2025")],
        rows=[
            ("Revenue", [(CURRENT_X, "1,000"), (PRIOR_X, "900")]),
            ("Profit for the period", [(CURRENT_X, "160"), (PRIOR_X, "120")]),
        ],
    )
    _statements, facts, _derived, _metrics = _run(write_pdf(tmp_path / "clean.pdf", [page]))
    assert _published(facts, "TOP_LINE")[0].normalized_value == Decimal("1000000")
    assert _published(facts, "PAT")[0].normalized_value == Decimal("160000")
    assert _published(facts, "PAT")[0].period_end == PERIOD_END
