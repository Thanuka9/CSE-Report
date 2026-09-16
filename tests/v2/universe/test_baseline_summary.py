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


def test_experiment_summary_is_diagnostic() -> None:
    path = ROOT / "tests" / "v2" / "universe" / "experiment_summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    freeze = json.loads(
        (ROOT / "tests" / "v2" / "universe" / "investigation_freeze.json").read_text(
            encoding="utf-8"
        )
    )
    baseline = json.loads(SUMMARY.read_text(encoding="utf-8"))
    ranking = json.loads(RANKING.read_text(encoding="utf-8"))
    sha = freeze["actual_code_sha"]
    assert payload["actual_code_sha"] == sha
    assert baseline["actual_code_sha"] == sha
    assert ranking["actual_code_sha"] == sha
    assert payload["source_snapshot_id"] == freeze["source_snapshot_id"]
    assert baseline["source_snapshot_id"] == freeze["source_snapshot_id"]
    assert payload["case_count"] == 33
    assert payload["g02_decision"] == "UNTESTED"
    assert payload["g02"]["facts_suppressed_by_cascade"] == 0
    assert payload["page_empty"]["production_router"] == "document"
    assert payload["page_empty"]["p1_ocr_applied"] is False
    assert "SOURCE_VALUE_NOT_REPRODUCIBLE" not in payload["lineage"]
    assert payload["lineage"].get("CONTEXT_EVIDENCE_INCOMPLETE", 0) >= 0
    assert payload.get("actual_code_sha")
    assert payload.get("prototypes", {}).get("h2") is False
    assert payload.get("prototypes", {}).get("u2") is False
    assert payload.get("prototypes", {}).get("p2") is False
    assert "not gold" in payload["note"].casefold() or "Diagnostic" in payload["note"]


def test_t10_score_artifact_is_not_certification() -> None:
    path = ROOT / "tests" / "v2" / "universe" / "t10_score.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["item_count"] == 40
    assert payload["gates"]["G01"]["decision"] == "KEEP"
    assert payload["gates"]["G03"]["decision"] == "KEEP"
    assert payload["gates"]["G09"]["decision"] == "KEEP"
    assert payload["gates"]["G02"]["decision"] == "UNTESTED"
    assert payload["gates"]["score"]["not_certification"] is True
    assert "holdout" in payload["note"].casefold()


def test_t25_holdout_score_is_diagnostic_not_cutover() -> None:
    path = ROOT / "tests" / "v2" / "universe" / "t25_holdout_score.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["split"] == "HOLDOUT"
    assert payload["item_count"] == 24
    assert payload["gates"]["score"]["not_certification"] is True
    cert = (ROOT / "docs" / "v2" / "EXTRACTION_CERTIFICATION_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert "NOT CERTIFIED" in cert
    assert "extraction.engine: v2" in cert



def test_investigation_status_blocks_cutover() -> None:
    text = (ROOT / "docs" / "v2" / "EXTRACTION_INVESTIGATION_STATUS.md").read_text(encoding="utf-8")
    assert "T29 Resume cutover" in text
    assert "BLOCKED" in text
    assert "engine: v2" in text
    assert "items.jsonl" in text
    assert (ROOT / "docs" / "v2" / "EXTRACTION_REPORT.md").is_file()


def test_defect_ranking_is_not_source_truth() -> None:
    payload = json.loads(RANKING.read_text(encoding="utf-8"))
    assert "Not source-confirmed" in payload["note"] or "not source" in payload["note"].casefold()
    assert payload["families"][0]["family"] == "MIXED_NATIVE_OCR"
    assert payload.get("actual_code_sha")
