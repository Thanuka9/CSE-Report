"""Triage N18 FN slots: NO_TARGET_CANDIDATE vs concept/context miss vs withheld."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v2_score_n18_ai_blind import _load_items, collect_n17_v2_facts, score_n18  # noqa: E402
from cse_financial_etl.v2.document.router import read_document  # noqa: E402
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline  # noqa: E402


def main() -> int:
    items = _load_items(ROOT / "tests/v2/source_truth/n17_ai_blind_gold.jsonl")
    identity = json.loads(
        (ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    facts = collect_n17_v2_facts(
        ROOT, ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json"
    )
    score = score_n18(items, facts)
    fns = [d for d in score["details"] if d.get("result") == "FN"]
    gold_by_key = {
        (i.issuer_id, i.metric_code): i
        for i in items
        if i.source_presence.value == "REPORTED"
    }

    # Collect traces per issuer for FN metrics
    traces_by_issuer: dict[str, list] = {}
    for row in identity.get("items") or ():
        issuer_id = str(row.get("issuer_id") or "")
        needed = {d["metric_code"] for d in fns if d["issuer_id"] == issuer_id}
        if not needed:
            continue
        pdf = ROOT / str(row.get("local_file") or "")
        if not pdf.is_file():
            continue
        doc = read_document(pdf, filing_version_id=str(row.get("filing_version_id") or ""))
        result = run_filing_pipeline(
            doc,
            issuer_id=issuer_id,
            issuer_name=str(row.get("legal_name") or ""),
            issuer_type=str(row.get("issuer_type") or ""),
        )
        traces_by_issuer[issuer_id] = list(result.traces or ())

    rows = []
    for d in fns:
        issuer = d["issuer_id"]
        metric = d["metric_code"]
        gold = gold_by_key.get((issuer, metric))
        traces = traces_by_issuer.get(issuer, [])
        resolved = [
            tr
            for tr in traces
            if getattr(tr, "resolved_metric", None) == metric
        ]
        near = []
        for tr in traces:
            alts = getattr(tr, "concept_alternatives", ()) or ()
            for alt in alts:
                if getattr(alt, "metric_code", None) == metric:
                    near.append(tr)
                    break
            label = (getattr(tr, "row_label", None) or "").lower()
            if gold and gold.raw_source_label and gold.raw_source_label.lower()[:24] in label:
                near.append(tr)

        if resolved:
            stages = [tr.first_failure_stage.value for tr in resolved if tr.first_failure_stage]
            family = "CANDIDATE_PRESENT_BUT_NOT_SOURCEFACT"
            stage = Counter(stages).most_common(1)[0][0] if stages else "UNKNOWN"
        elif near:
            stages = [tr.first_failure_stage.value for tr in near if tr.first_failure_stage]
            family = "NO_TARGET_CANDIDATE_NEAR_MISS"
            stage = Counter(stages).most_common(1)[0][0] if stages else "CONCEPT_UNRESOLVED"
        else:
            family = "NO_TARGET_CANDIDATE"
            stage = "NO_TARGET_CANDIDATE"

        rows.append(
            {
                "issuer_id": issuer,
                "metric_code": metric,
                "gold_value": d.get("truth"),
                "gold_label": None if gold is None else gold.raw_source_label,
                "gold_entity": None if gold is None or gold.entity_scope is None else gold.entity_scope.value,
                "gold_duration": None if gold is None else gold.duration_months,
                "gold_page": None if gold is None else gold.page,
                "family": family,
                "first_failure_stage": stage,
                "resolved_candidate_count": len(resolved),
                "near_miss_count": len(near),
                "example_near_labels": sorted(
                    {
                        (tr.row_label or "")[:80]
                        for tr in (resolved or near)[:5]
                    }
                )[:5],
            }
        )

    out_dir = ROOT / "tests/v2/universe/n18_fn_triage"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "id": "n18-fn-triage",
        "status": "TRIAGE",
        "fn_count": len(rows),
        "family_counts": dict(Counter(r["family"] for r in rows)),
        "stage_counts": dict(Counter(r["first_failure_stage"] for r in rows)),
        "by_metric": dict(Counter(r["metric_code"] for r in rows)),
        "by_issuer": dict(Counter(r["issuer_id"] for r in rows)),
        "note": (
            "NO_TARGET_CANDIDATE is not source-verified ROW_NOT_FOUND. "
            "CANDIDATE_PRESENT_BUT_NOT_SOURCEFACT means concept matched but admission/validation failed."
        ),
    }
    (out_dir / "n18_fn_triage.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "tests/v2/universe/n18_fn_triage_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    for r in rows:
        print(
            f"{r['issuer_id']:14} {r['metric_code']:18} {r['family']:32} "
            f"{r['first_failure_stage']:20} label={r['gold_label']!r}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
