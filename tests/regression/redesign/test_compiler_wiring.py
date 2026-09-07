"""Regression: redesign no-overpublication and compiler wiring."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from cse_financial_etl.tunnels.extraction_compiler import compile_filing


def test_compiler_seeds_from_layout_facts(tmp_path: Path) -> None:
    fact = ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="FLOW",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Profit for the period 100",
        unit_source_text="Rs.'000",
        confidence="HIGH",
        status="EXTRACTED",
        duration_months=3,
        comparison_role="CURRENT",
    )
    # Missing PDF — compiler seeded path still works with empty digest.
    pdf = tmp_path / "missing.pdf"
    pdf.write_bytes(b"%PDF-1.4 empty")
    result = compile_filing(
        pdf,
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        legacy_facts=[fact],
        run_tunnel_b_always=False,
    )
    assert result["report"]["tunnel_a"]["mode"] == "legacy_seeded"
    assert result["ledger"].accepted()
    assert result["report"]["filing_sha"]


def test_extract_filing_attaches_compiler_evidence() -> None:
    root = Path(__file__).resolve().parents[3]
    pdf = root / "data/raw/filings/HAYLEYS_FIBRE_PLC/2026-06-30_768_1785840975698.06.2026.pdf"
    if not pdf.exists():
        pytest.skip("Hayleys Fibre PDF not present")
    facts = extract_filing(
        pdf,
        "HAYLEYS FIBRE PLC",
        "HEXP.N0000",
        date(2026, 6, 30),
        ocr_enabled=False,
    )
    assert facts
    # At least one fact should carry compiler summary when enrichment succeeds.
    assert any(f.evidence_json and "compiler_report_summary" in f.evidence_json for f in facts)
