"""Image-only N17 slots: SDB + HUNA — no inventable values."""

from __future__ import annotations

import json
from pathlib import Path

REVIEWER = "chatgpt-blind-source-review-2026-09-19"
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
FLOW = {
    "PAT",
    "PBT",
    "OPERATING_PROFIT",
    "TOP_LINE",
    "EPS_BASIC",
    "EPS_DILUTED",
}

FILINGS = [
    {
        "filing_version_id": "SDB.N0000-2025-12-31",
        "issuer_id": "SDB.N0000",
        "pdf_sha256": "b1485b20467af08844d4e217eeb57bc38e7ccaf9c7eba0a7675f675d26c32c84",
        "entity_default": "BANK",
        "reason": "Image-only PDF (0 native text chars). Blind text-layer adjudication impossible without OCR/visual.",
    },
    {
        "filing_version_id": "HUNA.N0000-2025-12-31",
        "issuer_id": "HUNA.N0000",
        "pdf_sha256": "50277_fdb337ad0ebf6626",  # placeholder replaced below from manifest
        "entity_default": "COMPANY",
        "reason": "Image-only PDF (0 native text chars). Blind text-layer adjudication impossible without OCR/visual.",
    },
]


def main() -> int:
    identity = json.loads(
        Path("tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {it["filing_version_id"]: it for it in identity["items"]}
    out_dir = Path("outputs/n17_blind_partial")
    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in FILINGS:
        meta = by_id[spec["filing_version_id"]]
        rows = []
        for metric in METRICS:
            rows.append(
                {
                    "schema_version": "v2.0.0",
                    "filing_version_id": spec["filing_version_id"],
                    "pdf_sha256": meta["pdf_sha256"],
                    "issuer_id": spec["issuer_id"],
                    "metric_code": metric,
                    "source_presence": "AMBIGUOUS",
                    "raw_source_label": None,
                    "raw_source_value": None,
                    "normalized_value": None,
                    "entity_scope": None,
                    "period_end": "2025-12-31",
                    "duration_months": 3 if metric in FLOW else None,
                    "comparison_role": "CURRENT",
                    "currency": None,
                    "scale": None,
                    "unit_dimension": None,
                    "page": None,
                    "bbox": None,
                    "evidence_text": spec["reason"],
                    "evidence_level": "AMBIGUOUS",
                    "reviewer_1": REVIEWER,
                    "reviewer_2": None,
                    "adjudication_status": "AI_REVIEWER_1_COMPLETE",
                    "notes": "Blocked on image-only source; do not invent values. OCR/visual required.",
                    "split": "HOLDOUT",
                }
            )
        path = out_dir / f"{spec['issuer_id'].split('.')[0]}.jsonl"
        # issuer_id like SDB.N0000 -> SDB
        path = out_dir / f"{spec['issuer_id'].split('.')[0]}.jsonl"
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
        print("wrote", path, len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
