"""Generate blank N17 blind review queue from N16 identity (no values)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = [
    "PAT",
    "PBT",
    "OPERATING_PROFIT",
    "TOP_LINE",
    "EPS_BASIC",
    "EPS_DILUTED",
    "NAVPS",
    "TOTAL_EQUITY",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
]


def main() -> int:
    manifest = json.loads(
        (ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    items: list[dict] = []
    for filing in manifest["items"]:
        for metric in METRICS:
            items.append(
                {
                    "schema_version": "v2.0.0",
                    "filing_version_id": filing["filing_version_id"],
                    "pdf_sha256": filing["pdf_sha256"],
                    "issuer_id": filing["issuer_id"],
                    "metric_code": metric,
                    "local_file": filing["local_file"],
                    "source_presence": None,
                    "raw_source_label": None,
                    "raw_source_value": None,
                    "normalized_value": None,
                    "entity_scope": None,
                    "period_end": None,
                    "duration_months": None,
                    "comparison_role": None,
                    "currency": None,
                    "scale": None,
                    "unit_dimension": None,
                    "page": None,
                    "bbox": None,
                    "evidence_text": None,
                    "evidence_level": None,
                    "reviewer_1": None,
                    "reviewer_2": None,
                    "adjudication_status": "NOT_STARTED",
                    "notes": None,
                    "split": "HOLDOUT",
                }
            )
    queue = {
        "id": "n17-blind-review-queue-2026-09-16",
        "status": "READY_FOR_BLIND_ADJUDICATION",
        "recovery_step": "N17",
        "identity_manifest": "tests/v2/source_truth/holdout_v2_identity_manifest.json",
        "hard_rules": [
            "Reviewer must not see V1 values, V2 values, extraction results, or selector results.",
            "Use only the source PDF, Source Metric Truth Contract, and locked metric semantics.",
            "Do not invent values from memory of prior engine output.",
            "Do not score N16 until this queue is LOCKED as gold.",
            "Do not promote V2 / lower 8924.",
        ],
        "target_metrics": METRICS,
        "excluded_metrics_note": (
            "Exclude ROE, ROA, NPM, EPS_SELECTED, LIABILITIES_TO_EQUITY, LAST_TRADED_PRICE."
        ),
        "filing_count": len(manifest["items"]),
        "item_count": len(items),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Blank adjudication worksheet only. Null value fields are intentional. "
            "Completing this queue is human N17 work; this file is not locked gold."
        ),
        "items": items,
    }
    out = ROOT / "tests/v2/source_truth/n17_blind_review_queue.json"
    out.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    missing = [
        f["local_file"]
        for f in manifest["items"]
        if not (ROOT / f["local_file"]).exists()
    ]
    print(f"wrote {out} items={len(items)} filings={len(manifest['items'])}")
    print(f"missing_pdfs={len(missing)}")
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
