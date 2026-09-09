"""Evaluate a completed full-universe run without confusing proof gates with code failures."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

EXTERNAL_PROOF_GATES = {
    "GOLD_SAMPLE_INCOMPLETE",
    "GOLD_ISSUER_SAMPLE_INCOMPLETE",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    gates = list((manifest.get("production_gates") or {}).get("hits") or [])
    engineering_gates = [row for row in gates if row.get("code") not in EXTERNAL_PROOF_GATES]
    proof_gates = [row for row in gates if row.get("code") in EXTERNAL_PROOF_GATES]

    review_counts: Counter[str] = Counter()
    if args.review.exists():
        with args.review.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                review_counts[str(row.get("reason") or "UNKNOWN")] += 1

    payload = {
        "run_id": manifest.get("run_id"),
        "git_commit_sha": manifest.get("git_commit_sha"),
        "issuer_count": manifest.get("issuer_count"),
        "downloaded_filing_count": manifest.get("downloaded_filing_count"),
        "extracted_filing_count": manifest.get("extracted_filing_count"),
        "pipeline_error_count": manifest.get("pipeline_error_count"),
        "fact_status_counts": manifest.get("fact_status_counts"),
        "retry_summary": manifest.get("retry_summary"),
        "engineering_gate_count": len(engineering_gates),
        "engineering_gates": engineering_gates,
        "external_proof_gates": proof_gates,
        "review_failure_families": dict(review_counts.most_common()),
        "acceptance": (
            "ENGINEERING_PASS_EXTERNAL_PROOF_PENDING"
            if not engineering_gates and not int(manifest.get("pipeline_error_count") or 0)
            else "ENGINEERING_FAILURES_PRESENT"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["acceptance"] == "ENGINEERING_PASS_EXTERNAL_PROOF_PENDING" else 1


if __name__ == "__main__":
    raise SystemExit(main())
