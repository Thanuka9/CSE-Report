"""Final hardening checks for scope, sector and production gates."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cse_financial_etl.accounting.sector_profiles import profile_for_issuer
from cse_financial_etl.config import infer_entity_scope, load_issuers
from cse_financial_etl.sources.cse import DownloadedFiling, Filing
from cse_financial_etl.validation.production_gates import evaluate_production_gates
from tests.unit.redesign.test_eligibility_publisher import _layout_fact


def _downloaded(tmp_path: Path) -> DownloadedFiling:
    filing = Filing(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        filing_id=1,
        period_end=date(2026, 6, 30),
        title="Interim",
        source_path="x.pdf",
        source_url="https://example.invalid/x.pdf",
        uploaded_at=None,
        authorized_at=None,
    )
    return DownloadedFiling(filing, tmp_path / "x.pdf", "abc", 100)


def test_general_issuer_uses_general_corporate_profile() -> None:
    assert profile_for_issuer("ACME MANUFACTURING PLC").code == "GENERAL_CORPORATE"


def test_loaded_issuer_scope_is_used_by_downstream_inference(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "issuers.yml").write_text(
        "issuers:\n  ACME:\n    legal_name: Acme Bank Finance PLC\n"
        "    issuer_type: FINANCE_COMPANY\n    standalone_scope_label: COMPANY\n",
        encoding="utf-8",
    )
    load_issuers(tmp_path)
    assert infer_entity_scope("Acme Bank Finance PLC") == "COMPANY"


def test_explicit_layout_fallback_is_a_production_gate(tmp_path: Path) -> None:
    fact = _layout_fact(
        validation_status="PASSED",
        evidence_json=json.dumps({"explicit_fallback": "LAYOUT_FALLBACK_QUERY_MISS"}),
    )
    hits = evaluate_production_gates([(_downloaded(tmp_path), [fact])])
    assert "EXPLICIT_LAYOUT_FALLBACK_USED" in {hit.code for hit in hits}


def test_gold_gate_requires_independent_issuer_breadth() -> None:
    hits = evaluate_production_gates(
        [],
        golden_validation={
            "sample_size": 100,
            "passed": 100,
            "manual_issuer_count": 4,
            "results": [],
        },
        coverage_baseline={"min_gold_sample": 100, "min_gold_issuers": 100},
    )
    assert "GOLD_ISSUER_SAMPLE_INCOMPLETE" in {hit.code for hit in hits}
