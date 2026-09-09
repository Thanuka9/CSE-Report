"""Evaluate a completed full-universe run without confusing proof or quarantine with code failures."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from cse_financial_etl.validation.acceptance import is_publishable_fact

EXTERNAL_PROOF_GATES = {
    "GOLD_SAMPLE_INCOMPLETE",
    "GOLD_ISSUER_SAMPLE_INCOMPLETE",
}
TIMEOUT_PATTERN = re.compile(
    r"^PDF/OCR worker exceeded \d+(?:\.\d+)?s and its process tree was terminated$"
)


def _draft_publishable_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(
            1
            for row in csv.DictReader(handle)
            if is_publishable_fact(row, release_mode="DRAFT")
        )


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return [row for row in parsed if isinstance(row, dict)]


def _max_quarantined_timeouts(path: Path) -> int:
    if not path.exists():
        return 0
    parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return max(0, int(parsed.get("max_quarantined_extraction_timeouts") or 0))


def _classify_pipeline_errors(
    errors: list[dict[str, Any]],
    *,
    expected_count: int,
    max_quarantined_timeouts: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Separate bounded fail-closed PDF timeouts from genuine pipeline failures.

    A timeout is quarantine-eligible only when the resilient runner explicitly killed
    the extraction/OCR process tree. The exception remains visible in the artifact and
    review queue; this function changes only universe-level acceptance semantics.
    """

    quarantined: list[dict[str, Any]] = []
    unhandled: list[dict[str, Any]] = []
    for row in errors:
        stage = str(row.get("stage") or "")
        error = str(row.get("error") or "")
        if stage == "EXTRACTION" and TIMEOUT_PATTERN.fullmatch(error):
            quarantined.append(row)
        else:
            unhandled.append(row)

    if len(quarantined) > max_quarantined_timeouts:
        overflow = quarantined[max_quarantined_timeouts:]
        quarantined = quarantined[:max_quarantined_timeouts]
        unhandled.extend(
            {
                **row,
                "classification": "QUARANTINE_LIMIT_EXCEEDED",
                "quarantine_limit": max_quarantined_timeouts,
            }
            for row in overflow
        )

    if expected_count != len(errors):
        unhandled.append(
            {
                "stage": "ACCEPTANCE",
                "error": (
                    "pipeline_error_count mismatch: "
                    f"manifest={expected_count} artifact={len(errors)}"
                ),
                "classification": "PIPELINE_ERROR_EVIDENCE_MISMATCH",
            }
        )
    return quarantined, unhandled


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--facts", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    gates = list((manifest.get("production_gates") or {}).get("hits") or [])
    engineering_gates = [row for row in gates if row.get("code") not in EXTERNAL_PROOF_GATES]
    proof_gates = [row for row in gates if row.get("code") in EXTERNAL_PROOF_GATES]

    expected_error_count = int(manifest.get("pipeline_error_count") or 0)
    pipeline_errors = _load_json_list(args.errors)
    max_quarantined = _max_quarantined_timeouts(args.baseline)
    quarantined_errors, unhandled_errors = _classify_pipeline_errors(
        pipeline_errors,
        expected_count=expected_error_count,
        max_quarantined_timeouts=max_quarantined,
    )

    review_counts: Counter[str] = Counter()
    if args.review.exists():
        with args.review.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                review_counts[str(row.get("reason") or "UNKNOWN")] += 1

    engineering_pass = not engineering_gates and not unhandled_errors
    payload = {
        "run_id": manifest.get("run_id"),
        "git_commit_sha": manifest.get("git_commit_sha"),
        "issuer_count": manifest.get("issuer_count"),
        "downloaded_filing_count": manifest.get("downloaded_filing_count"),
        "extracted_filing_count": manifest.get("extracted_filing_count"),
        "pipeline_error_count": expected_error_count,
        "quarantined_pipeline_error_count": len(quarantined_errors),
        "quarantined_pipeline_errors": quarantined_errors,
        "unhandled_pipeline_error_count": len(unhandled_errors),
        "unhandled_pipeline_errors": unhandled_errors,
        "max_quarantined_extraction_timeouts": max_quarantined,
        "fact_status_counts": manifest.get("fact_status_counts"),
        "draft_publishable_count": _draft_publishable_count(args.facts),
        "retry_summary": manifest.get("retry_summary"),
        "engineering_gate_count": len(engineering_gates),
        "engineering_gates": engineering_gates,
        "external_proof_gates": proof_gates,
        "review_failure_families": dict(review_counts.most_common()),
        "acceptance": (
            "ENGINEERING_PASS_EXTERNAL_PROOF_PENDING"
            if engineering_pass
            else "ENGINEERING_FAILURES_PRESENT"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if engineering_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
