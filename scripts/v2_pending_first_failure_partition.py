"""Partition bridged V1 discovery candidates by first failed admission requirement.

Investigation-only. Does not change extraction floors or promote V2.
Samples pinned-cohort filings; writes pending_first_failure_partition.json.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "v1_v2_same_input" / "same_input_2026-09-09"


def _first_requirement_failure(candidate, *, registry) -> str:
    """Richer than source_admission_failure alone: ownership / duration / cmp."""

    from cse_financial_etl.v2.contracts.enums import ResolutionStatus, StatementType
    from cse_financial_etl.v2.resolution.resolver import source_admission_failure

    if candidate.source_ref is None or candidate.source_ref.bbox is None:
        return "SOURCE_ANCHOR_MISSING"
    if candidate.statement_id is None or not str(candidate.statement_id).strip():
        return "STATEMENT_OWNERSHIP_MISSING"

    # Statement hint unknown → concept matcher often abstains; call out ownership first
    # when concept is unresolved and statement typing is absent from reason notes.
    adm = source_admission_failure(candidate, registry=registry)
    if adm is not None and adm.value == "CONCEPT_UNRESOLVED":
        # Heuristic: table_id always present; treat absent concept as concept gate
        # unless row has no label (ownership of line item).
        if not (candidate.row_id and candidate.raw_value is not None):
            return "STATEMENT_OWNERSHIP_MISSING"
        return "CONCEPT_UNRESOLVED"
    if adm is not None:
        return adm.value

    # Admission OK for concept/entity/period/unit — still may lack duration/cmp for flows
    metric = None if candidate.concept is None else candidate.concept.metric_code
    flowish = metric in {
        "PAT",
        "PBT",
        "OPERATING_PROFIT",
        "TOP_LINE",
        "EPS_BASIC",
        "EPS_DILUTED",
    }
    if flowish and candidate.duration_status is ResolutionStatus.UNRESOLVED:
        return "DURATION_UNRESOLVED"
    if candidate.comparison_status is ResolutionStatus.UNRESOLVED:
        return "COMPARISON_ROLE_UNRESOLVED"
    return "ADMITTED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=42)
    parser.add_argument("--stride", type=int, default=0, help="If 0, auto stride over cohort")
    args = parser.parse_args()

    from cse_financial_etl.v2.challenger.observation_union import (
        observations_to_discovery_candidates,
    )
    from cse_financial_etl.v2.challenger.v1_source_observations import (
        collect_v1_source_observations,
    )
    from cse_financial_etl.v2.contracts.investigation import SOURCE_TARGET_METRICS
    from cse_financial_etl.v2.taxonomy.registry import load_registry

    cohort = json.loads((RUN / "pinned_cohort.json").read_text(encoding="utf-8"))
    filings = cohort["filings"]
    n = max(1, min(args.sample, len(filings)))
    stride = args.stride or max(1, len(filings) // n)
    sample = [filings[i] for i in range(0, len(filings), stride)][:n]

    registry = load_registry()
    all_fail: Counter[str] = Counter()
    target_fail: Counter[str] = Counter()
    still_discovery: Counter[str] = Counter()
    target_still_discovery: Counter[str] = Counter()
    filing_rows: list[dict] = []
    obs_total = 0
    cand_total = 0
    target_total = 0

    for item in sample:
        pdf = Path(item["abs_path"])
        symbol = item.get("symbol") or item["issuer_dir"]
        if not pdf.is_file():
            filing_rows.append({"issuer_dir": item["issuer_dir"], "error": "missing_pdf"})
            continue
        obs = collect_v1_source_observations(
            pdf,
            filing_version_id=f"{symbol}-{item['period_end']}",
            filing_id=str(symbol),
        )
        cands = observations_to_discovery_candidates(obs)
        obs_total += len(obs)
        cand_total += len(cands)
        local: Counter[str] = Counter()
        local_target: Counter[str] = Counter()
        for c in cands:
            fail = _first_requirement_failure(c, registry=registry)
            all_fail[fail] += 1
            local[fail] += 1
            discovery = "DISCOVERY_ONLY" in (c.reason_codes or ())
            if discovery:
                still_discovery[fail] += 1
            metric = None if c.concept is None else c.concept.metric_code
            if metric in SOURCE_TARGET_METRICS:
                target_total += 1
                target_fail[fail] += 1
                local_target[fail] += 1
                if discovery:
                    target_still_discovery[fail] += 1
        filing_rows.append(
            {
                "issuer_dir": item["issuer_dir"],
                "symbol": symbol,
                "period_end": item["period_end"],
                "observations": len(obs),
                "candidates": len(cands),
                "first_fail": dict(local),
                "target_first_fail": dict(local_target),
            }
        )
        print(
            f"{item['issuer_dir']}: obs={len(obs)} cand={len(cands)} "
            f"target={sum(local_target.values())}",
            flush=True,
        )

    out = {
        "sample_filings": len(sample),
        "filings_ok": sum(1 for r in filing_rows if "error" not in r),
        "observations_sum": obs_total,
        "candidates_sum": cand_total,
        "target_matched_candidates_sum": target_total,
        "first_fail_all": dict(all_fail.most_common()),
        "first_fail_target_matched": dict(target_fail.most_common()),
        "still_discovery_only_by_fail": dict(still_discovery.most_common()),
        "target_still_discovery_only_by_fail": dict(target_still_discovery.most_common()),
        "priority_note": (
            "Do not engineer on CONCEPT_UNRESOLVED mass (non-target cells). "
            "Among target-matched, prioritize PERIOD → UNIT → ENTITY; then duration/cmp."
        ),
        "filings": filing_rows,
    }
    path = RUN / "pending_first_failure_partition.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in out if k != "filings"}, indent=2))
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
