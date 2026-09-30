"""Build the deterministic 100-issuer MANUAL_QA adjudication packet.

Does not invent gold. PIPELINE_SEEDED and MANUAL_OR_PRIOR rows stay unsigned until
an independent reviewer marks them MANUAL_QA against the source PDF.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "golden_financial_facts.json"
OUT_DIR = ROOT / "reports" / "gold_gate"
PACKET = OUT_DIR / "manual_qa_adjudication_packet.json"
QUEUE_CSV = OUT_DIR / "manual_qa_adjudication_queue.csv"


def main() -> None:
    fixtures = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if not isinstance(fixtures, list):
        raise SystemExit("golden_financial_facts.json must be a list")

    by_status = Counter(str(row.get("verification_status") or "UNKNOWN") for row in fixtures)
    manual_qa = [row for row in fixtures if row.get("verification_status") == "MANUAL_QA"]
    pending = [
        row
        for row in fixtures
        if row.get("verification_status") != "MANUAL_QA"
    ]
    pending.sort(key=lambda row: (str(row.get("symbol") or ""), str(row.get("period_end") or "")))

    queue_rows = []
    for index, row in enumerate(pending, start=1):
        queue_rows.append(
            {
                "queue_index": index,
                "issuer_name": row.get("issuer_name"),
                "symbol": row.get("symbol"),
                "period_end": row.get("period_end"),
                "entity_scope": row.get("entity_scope"),
                "issuer_type": row.get("issuer_type"),
                "pdf": row.get("pdf"),
                "current_verification_status": row.get("verification_status"),
                "fact_codes": ",".join(sorted((row.get("facts") or {}).keys())),
                "price_symbols": ",".join(sorted((row.get("prices") or {}).keys())),
                "adjudication_status": "PENDING_INDEPENDENT_REVIEW",
                "reviewer": "",
                "decision": "",
                "notes": "",
            }
        )

    packet = {
        "contract": "coverage_baseline.yml min_gold_issuers=100 counts MANUAL_QA only",
        "fixture": str(FIXTURE.relative_to(ROOT)).replace("\\", "/"),
        "issuer_count": len(fixtures),
        "by_verification_status": dict(by_status),
        "manual_qa_issuer_count": len(manual_qa),
        "manual_qa_issuers": [
            {
                "issuer_name": row.get("issuer_name"),
                "symbol": row.get("symbol"),
                "period_end": row.get("period_end"),
            }
            for row in sorted(manual_qa, key=lambda row: str(row.get("symbol") or ""))
        ],
        "remaining_independent_reviews": len(pending),
        "required_manual_qa_issuers": 100,
        "deficit": max(0, 100 - len(manual_qa)),
        "instructions": [
            "Open the source PDF listed for each queue row.",
            "Confirm each fixture fact and price against the PDF.",
            "Do not copy pipeline output, V1 ledgers, or V2 workbooks.",
            "Only after independent confirmation may verification_status become MANUAL_QA.",
            "Do not bulk-relabel PIPELINE_SEEDED as MANUAL_QA.",
        ],
        "queue_csv": str(QUEUE_CSV.relative_to(ROOT)).replace("\\", "/"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PACKET.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    with QUEUE_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(queue_rows[0]) if queue_rows else [])
        if queue_rows:
            writer.writeheader()
            writer.writerows(queue_rows)
    print(
        f"wrote {PACKET.relative_to(ROOT)} "
        f"(MANUAL_QA={len(manual_qa)} pending={len(pending)} deficit={packet['deficit']})"
    )


if __name__ == "__main__":
    main()
