"""Adversarial cross-page continuation cases.

The extractor must align continuation columns from source-owned financial header
semantics, never from page-local column indexes, and ambiguous entity cues must
remain unresolved.
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
    assert len(hits) == 1, [
        (f.status, f.normalized_value, f.source_line) for f in facts if f.metric_code == code
    ]
    return hits[0]


def test_continuation_survives_page_local_note_column_shift(tmp_path: Path) -> None:
    """A NOTE column may disappear on page 2 without changing financial column identity."""

    first = statement_page(
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

    facts = _extract(write_pdf(tmp_path / "continuation_note_shift.pdf", [first, continuation]))
    assert _one(facts, "TOP_LINE").normalized_value == Decimal("1000000")
    assert _one(facts, "PBT").normalized_value == Decimal("200000")
    assert _one(facts, "PAT").normalized_value == Decimal("160000")


def test_ambiguous_continuation_entity_cannot_be_collapsed(tmp_path: Path) -> None:
    """A compound GROUP/COMPANY cue is not a single source-owned entity."""

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
        extra_bottom_lines=["Entity scope is intentionally ambiguous on this continuation page"],
    )

    facts = _extract(write_pdf(tmp_path / "continuation_entity_ambiguous.pdf", [first, continuation]))
    assert not [fact for fact in facts if fact.metric_code in {"PBT", "PAT"} and _published(fact)]
