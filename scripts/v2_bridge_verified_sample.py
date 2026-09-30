"""Evaluate context-bridge recovery on stratified filings (DEV sample, not unseen).

Compares V2-only vs V1-assisted selected draft-publishable TARGET facts.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "v1_v2_same_input" / "same_input_2026-09-09"
TARGET = {
    "TOP_LINE",
    "OPERATING_PROFIT",
    "PBT",
    "PAT",
    "EPS_BASIC",
    "EPS_DILUTED",
    "NAVPS",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    from cse_financial_etl.v2.contracts.enums import EntityScope
    from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
    from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts

    cohort = json.loads((RUN / "pinned_cohort.json").read_text(encoding="utf-8"))
    # Prefer filings whose titles suggest Group/Company headers (bridge-friendly).
    preferred = []
    rest = []
    for item in cohort["filings"]:
        name = (item.get("legal_name") or item["issuer_dir"]).upper()
        bucket = preferred if any(x in name for x in ()) else rest
        # Stratify by period round-robin from full list
        rest.append(item)
    # Deterministic stratified sample: every Nth filing, capped
    step = max(1, len(rest) // args.limit)
    sample = rest[::step][: args.limit]

    rows = []
    totals = Counter()
    for item in sample:
        pdf = Path(item["abs_path"])
        symbol = str(item.get("symbol") or item["issuer_dir"])
        period = date.fromisoformat(item["period_end"])
        legal = str(item.get("legal_name") or "")
        try:
            v2 = run_pdf_pipeline(
                pdf,
                issuer_id=symbol,
                filing_version_id=f"{symbol}-{period}-v2",
                issuer_name=legal,
                v1_source_observations=False,
            )
            assisted = run_pdf_pipeline(
                pdf,
                issuer_id=symbol,
                filing_version_id=f"{symbol}-{period}-as",
                issuer_name=legal,
                v1_source_observations=True,
            )
        except Exception as exc:  # noqa: BLE001
            rows.append({"issuer_dir": item["issuer_dir"], "period_end": item["period_end"], "error": str(exc)})
            totals["errors"] += 1
            continue

        # Lock expected entity to the first non-empty V2 selection so assisted
        # comparison cannot flip GROUP↔COMPANY and invent false losses.
        ent0, sel0 = None, ()
        for ent in (EntityScope.COMPANY, EntityScope.GROUP, EntityScope.BANK):
            sel = select_pipeline_facts(v2.source_facts, period_end=period, expected_entity=ent)
            if sel:
                ent0, sel0 = ent, sel
                break
        if ent0 is None:
            ent1, sel1 = None, ()
            for ent in (EntityScope.COMPANY, EntityScope.GROUP, EntityScope.BANK):
                sel = select_pipeline_facts(
                    assisted.source_facts, period_end=period, expected_entity=ent
                )
                if sel:
                    ent1, sel1 = ent, sel
                    break
        else:
            ent1 = ent0
            sel1 = select_pipeline_facts(
                assisted.source_facts, period_end=period, expected_entity=ent0
            )
        keys0 = {(f.metric_code, f.entity_scope.value, str(f.normalized_value)) for f in sel0 if f.metric_code in TARGET}
        keys1 = {(f.metric_code, f.entity_scope.value, str(f.normalized_value)) for f in sel1 if f.metric_code in TARGET}
        gained = keys1 - keys0
        lost = keys0 - keys1
        totals["filings"] += 1
        totals["selected_v2"] += len(keys0)
        totals["selected_assisted"] += len(keys1)
        totals["gained"] += len(gained)
        totals["lost"] += len(lost)
        if gained:
            totals["filings_with_gain"] += 1
        rows.append(
            {
                "issuer_dir": item["issuer_dir"],
                "period_end": item["period_end"],
                "symbol": symbol,
                "select_entity_v2": None if ent0 is None else ent0.value,
                "select_entity_assisted": None if ent1 is None else ent1.value,
                "selected_v2": len(keys0),
                "selected_assisted": len(keys1),
                "gained": sorted(list(gained))[:20],
                "lost": sorted(list(lost))[:20],
                "eligible_v2": sum(1 for f in v2.source_facts if f.publication_status.value == "ELIGIBLE"),
                "eligible_assisted": sum(
                    1 for f in assisted.source_facts if f.publication_status.value == "ELIGIBLE"
                ),
            }
        )
        print(
            f"{item['issuer_dir']} {item['period_end']} "
            f"sel {len(keys0)}->{len(keys1)} gained={len(gained)} lost={len(lost)}"
        )

    out = {
        "id": "verified-bridge-sample",
        "run_id": "same_input_2026-09-09",
        "sample_size": len(sample),
        "totals": dict(totals),
        "rows": rows,
        "note": (
            "DEV stratified sample for bridge lift. Selection uses first non-empty of "
            "GROUP/COMPANY/BANK expected entity. Not a population correctness claim."
        ),
    }
    path = RUN / "verified_bridge_sample_summary.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out["totals"], indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
