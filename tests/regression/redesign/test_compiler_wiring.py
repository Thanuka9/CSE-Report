"""Regression: redesign compiler is the publish path (not silent layout)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from cse_financial_etl.facts.publisher import publish_from_compiler
from cse_financial_etl.storage.stage_cache import StageCache, cache_key, default_version_vector
from cse_financial_etl.tunnels.extraction_compiler import compile_filing
from cse_financial_etl.validation.eval_harness import run_offline_eval


def test_compiler_layout_assist_mode(tmp_path: Path) -> None:
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
    pdf = tmp_path / "missing.pdf"
    pdf.write_bytes(b"%PDF-1.4 empty")
    result = compile_filing(
        pdf,
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        legacy_facts=[fact],
        compile_statements=False,
        run_tunnel_b_always=False,
    )
    mode = result["report"]["tunnel_a"]["mode"]
    assert mode in {"layout_assist_compiler", "full_compiler_with_layout_assist"}
    assert result["ledger"].accepted()
    assert result["report"]["filing_sha"] is not None
    published, stats = publish_from_compiler(
        queried=result["queried"],
        layout_facts=[fact],
        report=result["report"],
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        required_entity="COMPANY",
    )
    pat = next(f for f in published if f.metric_code == "PAT")
    assert pat.status == "EXTRACTED"
    assert pat.extraction_method == "COMPILER_QUERY"
    assert pat.normalized_value == Decimal("100000")
    evidence = json.loads(pat.evidence_json or "{}")
    assert evidence["publication_path"] == "statement_compiler"
    assert stats["explicit_layout_fallback"] == 0


def test_extract_filing_publishes_via_compiler() -> None:
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
    assert any(f.extraction_method == "COMPILER_QUERY" for f in facts if f.status == "EXTRACTED")
    assert any(
        f.evidence_json and "publication_path" in f.evidence_json for f in facts
    )
    # No silent layout-only publish for extracted core facts.
    for fact in facts:
        if fact.status != "EXTRACTED":
            continue
        if fact.metric_code in {"CROSS_METRIC_CONTEXT"}:
            continue
        evidence = json.loads(fact.evidence_json or "{}")
        assert evidence.get("publication_path") in {
            "statement_compiler",
            "explicit_layout_fallback",
        }
        if evidence.get("publication_path") == "explicit_layout_fallback":
            assert evidence.get("issue_code")


def test_stage_cache_roundtrip(tmp_path: Path) -> None:
    cache = StageCache(tmp_path / "cache")
    key = cache_key(
        source_sha256="abc",
        stage="extraction_report",
        versions=default_version_vector(),
    )
    cache.put_json(key, {"ok": True})
    assert cache.get_json(key) == {"ok": True}


def test_offline_eval_harness_smoke() -> None:
    root = Path(__file__).resolve().parents[3]
    summary = run_offline_eval(root, cases=[], compile_statements=False)
    assert summary["case_count"] == 0
    assert "tracked_metrics" in summary
