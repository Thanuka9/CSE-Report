"""Release certification after 829 hybrid parity.

Does not set extraction.engine: v2. READY FOR OFFICIAL DECISION is emitted
only when every gate in this pack actually passes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARITY = ROOT / "reports/v1_v2_same_input/hybrid_baseline_full829_unionfix"
HOLDOUT_IDENTITY = ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json"
E13_SUMMARY = ROOT / "tests/v2/universe/e13_v2_challenger_clean_d29b392/e13_summary.json"
COHORT = (
    ROOT
    / "reports/v1_v2_same_input/alias_pct_other_selrank_full829_2026-09-20/pinned_cohort.json"
)


def _run(cmd: list[str], *, timeout: int = 1800) -> dict[str, Any]:
    result = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "stdout_tail": (result.stdout or "")[-4000:],
        "stderr_tail": (result.stderr or "")[-4000:],
    }


def _engine_still_v1() -> dict[str, Any]:
    app = yaml.safe_load((ROOT / "configs" / "app.yml").read_text(encoding="utf-8"))
    engine = app.get("extraction", {}).get("engine")
    return {
        "passed": engine == "v1",
        "detail": f"configs/app.yml extraction.engine={engine!r}; flip only after human approval",
    }


def _parity_gate(parity_dir: Path) -> dict[str, Any]:
    summary_path = parity_dir / "hybrid_parity_summary.json"
    if not summary_path.exists():
        return {"passed": False, "detail": f"missing {summary_path}"}
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    disagreements_path = parity_dir / "disagreements.csv"
    class_counts: dict[str, int] = dict(summary.get("classification_counts") or {})
    if disagreements_path.exists():
        with disagreements_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                class_counts[row["classification"]] = class_counts.get(row["classification"], 0) + 0
    unexplained = int(summary.get("unexplained_losses_or_mismatches") or 0)
    completed = int(summary.get("filings_completed") or 0)
    attempted = int(summary.get("filings_attempted") or 0)
    errors = int(summary.get("filings_error_non_ocr") or summary.get("filings_error") or 0)
    ocr = int(summary.get("filings_ocr_quarantine") or 0)
    if "filings_error_non_ocr" in summary:
        errors = int(summary.get("filings_error_non_ocr") or 0)
    passed = bool(summary.get("parity_pass")) and completed == attempted == 829 and unexplained == 0 and errors == 0
    return {
        "passed": passed,
        "detail": (
            f"completed={completed}/{attempted} non_ocr_errors={errors} ocr_quarantine={ocr} "
            f"unexplained={unexplained} coverage={summary.get('coverage_vs_v1')} "
            f"classes={summary.get('classification_counts')}"
        ),
        "summary": {k: v for k, v in summary.items() if k != "errors"},
    }


def _holdout_from_parity(parity_dir: Path) -> dict[str, Any]:
    identity = json.loads(HOLDOUT_IDENTITY.read_text(encoding="utf-8"))
    holdout_shas = {
        item["pdf_sha256"]
        for item in identity.get("items") or ()
        if isinstance(item, dict) and item.get("pdf_sha256")
    }
    disagreements_path = parity_dir / "disagreements.csv"
    if not disagreements_path.exists():
        return {"passed": False, "detail": "disagreements.csv missing; cannot slice holdout"}
    holdout_rows = []
    unexplained = 0
    with disagreements_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("pdf_sha256") not in holdout_shas:
                continue
            holdout_rows.append(row)
            if str(row.get("classification") or "").startswith("UNEXPLAINED"):
                unexplained += 1
    overlap = 0
    progress = parity_dir / "progress.jsonl"
    if progress.exists():
        done = {
            json.loads(line).get("pdf_sha256")
            for line in progress.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        overlap = len(done & holdout_shas)
    passed = overlap == len(holdout_shas) and unexplained == 0 and len(holdout_shas) > 0
    return {
        "passed": passed,
        "detail": (
            f"N16 identity {len(holdout_shas)} SHAs; overlap_with_829={overlap}; "
            f"holdout_disagreements={len(holdout_rows)}; unexplained={unexplained}. "
            "Identity-only preservation, not N17 blind gold scoring."
        ),
        "holdout_sha_count": len(holdout_shas),
        "overlap": overlap,
        "unexplained": unexplained,
        "disagreement_sample": holdout_rows[:20],
    }


def _e13_governed_coverage() -> dict[str, Any]:
    floors = _run([sys.executable, "scripts/check_coverage_floors.py"])
    e13 = json.loads(E13_SUMMARY.read_text(encoding="utf-8")) if E13_SUMMARY.exists() else {}
    baseline = yaml.safe_load((ROOT / "configs" / "coverage_baseline.yml").read_text(encoding="utf-8"))
    floor = baseline.get("min_draft_publishable")
    historic = e13.get("draft_publishable_count")
    return {
        "passed": bool(floors["passed"]) and floor == 8924,
        "detail": (
            f"floor_script_ok={floors['passed']}; min_draft_publishable={floor}; "
            f"historic_E13_draft_publishable={historic} (challenger, not a lowered floor). "
            "Hybrid TARGET parity is not the E13 source+derived 8,924 definition."
        ),
        "floor_script": floors,
        "historic_e13": {
            "draft_publishable_count": historic,
            "downloaded_filing_count": e13.get("downloaded_filing_count"),
            "min_draft_publishable_floor": e13.get("min_draft_publishable_floor"),
        },
    }


def _pytest_gate(name: str, paths: list[str]) -> dict[str, Any]:
    result = _run([sys.executable, "-m", "pytest", "-q", *paths], timeout=2400)
    result["name"] = name
    return result


def _remote_ci() -> dict[str, Any]:
    probe = _run(["gh", "auth", "status"], timeout=60)
    if not probe["passed"]:
        return {
            "passed": False,
            "detail": "gh auth is not available; remote CI not dispatched",
            "probe": probe,
        }
    dispatched = _run(
        [
            "gh",
            "workflow",
            "run",
            "full-production-validation.yml",
            "--ref",
            "v2/extraction-investigation",
        ],
        timeout=60,
    )
    return {
        "passed": bool(dispatched["passed"]),
        "detail": "workflow_dispatch full-production-validation.yml"
        if dispatched["passed"]
        else dispatched.get("stderr_tail") or "dispatch failed",
        "dispatch": dispatched,
    }


def _replay(parity_dir: Path, n: int = 3) -> dict[str, Any]:
    cohort = json.loads(COHORT.read_text(encoding="utf-8"))
    progress = parity_dir / "progress.jsonl"
    done = []
    if progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.append(json.loads(line).get("pdf_sha256"))
    by_sha = {item["pdf_sha256"]: item for item in cohort["filings"]}
    sample = []
    if progress.exists():
        for line in progress.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            sha = row.get("pdf_sha256")
            if sha not in by_sha:
                continue
            if int(row.get("v1") or 0) <= 0:
                continue
            sample.append(by_sha[sha])
            if len(sample) >= n:
                break
    if len(sample) < n:
        return {"passed": False, "detail": f"need {n} completed SHAs for replay, got {len(sample)}"}
    sys.path.insert(0, str(ROOT / "scripts"))
    from v2_hybrid_parity_measure import _hybrid_rows  # type: ignore

    mismatches = []
    for item in sample:
        first = _hybrid_rows(item)
        second = _hybrid_rows(item)
        def fingerprint(rows: list[dict[str, Any]]) -> str:
            payload = sorted(
                (
                    row.get("metric_code"),
                    row.get("entity_scope"),
                    row.get("period_end"),
                    str(row.get("normalized_value")),
                    row.get("publication_status"),
                )
                for row in rows
            )
            return hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()

        if fingerprint(first) != fingerprint(second):
            mismatches.append(item["pdf_sha256"])
    return {
        "passed": not mismatches,
        "detail": f"replayed {len(sample)} PDFs twice; mismatches={len(mismatches)}",
        "sample_shas": [item["pdf_sha256"] for item in sample],
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parity-dir", type=Path, default=DEFAULT_PARITY)
    parser.add_argument("--skip-replay", action="store_true")
    parser.add_argument("--skip-remote-ci", action="store_true")
    args = parser.parse_args()
    args.parity_dir.mkdir(parents=True, exist_ok=True)

    gates: dict[str, dict[str, Any]] = {}
    gates["hybrid_829_parity"] = _parity_gate(args.parity_dir)
    gates["engine_remains_v1"] = _engine_still_v1()
    gates["e13_governed_coverage"] = _e13_governed_coverage()
    gates["fresh_unseen_holdout_identity"] = _holdout_from_parity(args.parity_dir)
    gates["lineage_completeness"] = _pytest_gate(
        "lineage",
        ["tests/v2/unit/test_lineage_audit.py", "tests/v2/unit/test_resolver_and_validation.py"],
    )
    gates["ocr_quarantine"] = _pytest_gate(
        "ocr",
        [
            "tests/v2/unit/test_page_routing.py",
            "tests/v2/unit/test_ocr_runtime_packaging.py",
        ],
    )
    gates["workbook_reconciliation"] = _pytest_gate(
        "workbook",
        [
            "tests/v2/unit/test_workbook_v2.py",
            "tests/v2/unit/test_workbook_dispatch.py",
        ],
    )
    gates["rollback"] = _pytest_gate(
        "rollback",
        ["tests/v2/unit/test_production_engine.py", "tests/v2/unit/test_v1_baseline_union.py"],
    )
    gates["v2_unit_suite"] = _pytest_gate("v2_unit", ["tests/v2/unit"])
    if args.skip_replay:
        gates["deterministic_replay"] = {"passed": False, "detail": "skipped"}
    else:
        gates["deterministic_replay"] = _replay(args.parity_dir)
    if args.skip_remote_ci:
        gates["remote_ci"] = {"passed": False, "detail": "skipped"}
    else:
        gates["remote_ci"] = _remote_ci()

    all_passed = all(bool(gate.get("passed")) for gate in gates.values())
    status = "READY FOR OFFICIAL DECISION" if all_passed else "NOT READY — FAILED GATE"
    pack = {
        "id": "hybrid-parity-release-certification",
        "status": status,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "production_engine": "v1",
        "human_approval_required_before_engine_v2": True,
        "gates": {
            name: {
                "passed": bool(gate.get("passed")),
                "detail": gate.get("detail") or gate.get("stdout_tail") or gate.get("stderr_tail"),
                **{
                    key: value
                    for key, value in gate.items()
                    if key not in {"stdout_tail", "stderr_tail", "dispatch", "probe", "floor_script"}
                },
            }
            for name, gate in gates.items()
        },
        "failed_gates": [name for name, gate in gates.items() if not gate.get("passed")],
        "note": (
            "Do not set extraction.engine: v2 until a human records OFFICIAL approval. "
            "V1 remains the internal fallback backend."
        ),
    }
    out = args.parity_dir / "release_certification.json"
    out.write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": status, "failed_gates": pack["failed_gates"]}, indent=2))
    print(f"wrote {out}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
