"""Summarize residual N18 period/unit mismatches after UBC OP fix."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from v2_score_n18_ai_blind import _load_items, collect_n17_v2_facts, score_n18  # noqa: E402


def main() -> int:
    items = _load_items(ROOT / "tests/v2/source_truth/n17_ai_blind_gold.jsonl")
    facts = collect_n17_v2_facts(
        ROOT, ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json"
    )
    score = score_n18(items, facts)
    mismatches = [d for d in score["details"] if d.get("result") == "MISMATCH"]
    period = [d for d in mismatches if "period" in d.get("mismatch_kinds", [])]
    unit = [d for d in mismatches if "unit" in d.get("mismatch_kinds", [])]
    duration = [d for d in mismatches if "duration" in d.get("mismatch_kinds", [])]
    summary = {
        "id": "n18-residual-mismatch-triage",
        "tp": score["tp"],
        "fn": score["fn"],
        "critical_wrong": score["critical_wrong"],
        "mismatch_count": len(mismatches),
        "period_mismatch_count": len(period),
        "unit_mismatch_count": len(unit),
        "duration_mismatch_count": len(duration),
        "period_by_issuer": dict(Counter(d["issuer_id"] for d in period)),
        "period_by_metric": dict(Counter(d["metric_code"] for d in period)),
        "unit_by_issuer": dict(Counter(d["issuer_id"] for d in unit)),
        "unit_by_metric": dict(Counter(d["metric_code"] for d in unit)),
        "period_rows": period,
        "unit_rows": unit,
        "duration_rows": duration,
    }
    out = ROOT / "tests/v2/universe/n18_residual_mismatch_triage.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k.endswith("_count") or k in {"tp", "fn", "critical_wrong", "period_by_issuer", "unit_by_metric"}}, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
