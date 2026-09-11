"""Regression: redesign compiler is the publish path (not silent layout)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, extract_filing
from cse_financial_etl.storage.stage_cache import StageCache, cache_key, default_version_vector
from cse_financial_etl.tunnels.extraction_compiler import compile_filing
from cse_financial_etl.validation.eval_harness import run_offline_eval
from tests.fixture_paths import real_pdf


def test_compiler_layout_assist_mode_is_discovery_only(tmp_path: Path) -> None:
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
    assert not result["ledger"].accepted()
    assert result["report"]["filing_sha"] is not None

    entries = result["ledger"].entries
    assert len(entries) == 1
    entry = entries[0]
    assert entry.evidence["candidate_origin"] == "layout_geometry"
    assert entry.evidence["context_not_source_owned"] is True
    assert entry.entity is None
    assert entry.period_end is None
    assert entry.comparison_role is None
    assert not any(
        queried.entry is not None and queried.metric_code == "PAT"
        for queried in result["queried"]
    )


def test_extract_filing_publishes_via_compiler() -> None:
    pdf = real_pdf("HAYLEYS_FIBRE_PLC/2026-06-30_768_1785840975698.06.2026.pdf")
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
        assert evidence.get("publication_routing") == "statement_compiler"
        assert evidence.get("native_compiler_success") is True
        assert evidence.get("explicit_fallback") is None


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
