from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SUMMARY = ROOT / "tests" / "v2" / "universe" / "baseline_run_summary.json"
MANIFEST = ROOT / "tests" / "v2" / "universe" / "locked_source_manifest.json"
RANKING = ROOT / "tests" / "v2" / "universe" / "defect_family_ranking.json"


def test_locked_baseline_was_deterministic() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["case_count"] == 33
    assert summary["all_deterministic"] is True
    assert summary["include_v1"] is True
    assert summary["derived_audit"]["DERIVED_COMPLETE"] == summary["derived_facts"]
    assert "NOT_ADJUDICATED" in summary["note"]
    assert summary["disagreement"]["REFERENCE_ONLY_DISAGREEMENT"] >= 0


def test_locked_source_manifest_has_sha_set() -> None:
    rows = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(rows) == 33
    shas = {row["pdf_sha256"] for row in rows}
    assert len(shas) == 33
    assert all(len(row["pdf_sha256"]) == 64 for row in rows)
    assert all(not row["local_file"].startswith("D:") for row in rows)


def test_defect_ranking_is_not_source_truth() -> None:
    payload = json.loads(RANKING.read_text(encoding="utf-8"))
    assert "Not source-confirmed" in payload["note"] or "not source" in payload["note"].casefold()
    assert payload["families"][0]["family"] == "MIXED_NATIVE_OCR"
