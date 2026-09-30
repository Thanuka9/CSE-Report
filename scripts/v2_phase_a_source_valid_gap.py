"""Phase A: same-input source-valid gap + selection waterfall (final execution plan).

Builds differentials and selection funnel from frozen three-way ledgers.
Stratifies a PDF-review queue. Optionally probes first-loss on a V1-only sample
via live assisted pipeline. Does not promote V2 or change floors.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "reports" / "v1_v2_same_input" / "same_input_2026-09-09"
OUT = ROOT / "reports" / "v1_v2_same_input" / "phase_a_2026-09-20"
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


def _dec(v: str | None) -> str:
    if v is None or str(v).strip() == "":
        return ""
    try:
        return str(Decimal(str(v).replace(",", "")))
    except (InvalidOperation, ValueError):
        return str(v).strip()


def _key(row: dict[str, str], *, value_field: str = "normalized_value") -> tuple:
    dur = (row.get("duration_months") or "").strip()
    val = _dec(row.get(value_field) or row.get("raw_text"))
    return (
        row.get("symbol") or row.get("issuer_dir") or "",
        row.get("metric_code") or "",
        row.get("entity_scope") or "",
        row.get("period_end") or "",
        dur,
        row.get("comparison_role") or "",
        val,
    )


def _soft_key(row: dict[str, str]) -> tuple:
    dur = (row.get("duration_months") or "").strip()
    return (
        row.get("symbol") or row.get("issuer_dir") or "",
        row.get("metric_code") or "",
        row.get("entity_scope") or "",
        row.get("period_end") or "",
        dur,
        row.get("comparison_role") or "",
    )


def _load(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def selection_funnel(rows: list[dict[str, str]]) -> dict[str, int]:
    eligible = [r for r in rows if r.get("publication_status") == "ELIGIBLE"]
    current = [r for r in eligible if (r.get("comparison_role") or "") == "CURRENT"]
    quarterish = [
        r
        for r in current
        if (r.get("duration_months") or "").strip() in {"", "3"}
        or r.get("metric_code")
        in {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES", "NAVPS"}
    ]
    # Prefer COMPANY/BANK then GROUP like measure script
    by_filing: dict[str, list] = defaultdict(list)
    for r in quarterish:
        by_filing[r.get("pdf_sha256") or r.get("symbol") or ""].append(r)
    selected = 0
    for _fid, items in by_filing.items():
        for pref in ("COMPANY", "BANK", "GROUP", "CONSOLIDATED", "SEPARATE"):
            hit = [r for r in items if (r.get("entity_scope") or "") == pref]
            if not hit:
                continue
            # unique by metric
            seen: set[str] = set()
            for r in hit:
                m = r.get("metric_code") or ""
                if m in seen:
                    continue
                seen.add(m)
                if m in TARGET:
                    selected += 1
            break
    return {
        "target_rows": len(rows),
        "eligible_rows": len(eligible),
        "eligible_current": len(current),
        "eligible_current_quarterish": len(quarterish),
        "approx_selected_target": selected,
        "ledger_draft_selected_true": sum(
            1 for r in rows if str(r.get("draft_selected")).lower() == "true"
        ),
    }


def stratify_sample(rows: list[dict[str, str]], *, n: int, seed: int = 20) -> list[dict]:
    rng = random.Random(seed)
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        issuer = (r.get("issuer_dir") or "").upper()
        if "BANK" in issuer or issuer.endswith("_PLC") and "BANK" in issuer:
            sector = "BANK"
        elif any(x in issuer for x in ("FINANCE", "LEASING", "INSUR", "TAKAFUL", "CAPITAL")):
            sector = "FINANCE_INSURANCE"
        else:
            sector = "GENERAL"
        metric = r.get("metric_code") or "?"
        entity = r.get("entity_scope") or "?"
        buckets[f"{sector}|{metric}|{entity}"].append(r)
    keys = sorted(buckets)
    sample: list[dict] = []
    # round-robin
    while len(sample) < n and keys:
        for k in list(keys):
            if not buckets[k]:
                keys.remove(k)
                continue
            sample.append(buckets[k].pop(rng.randrange(len(buckets[k]))))
            if len(sample) >= n:
                break
    return sample


def probe_first_loss(item: dict, cohort_item: dict) -> dict:
    """Classify where a V1-only key fails in V2-only and assisted pipelines."""

    from cse_financial_etl.v2.challenger.observation_union import (
        observations_to_discovery_candidates,
    )
    from cse_financial_etl.v2.challenger.v1_source_observations import (
        collect_v1_source_observations,
    )
    from cse_financial_etl.v2.contracts.enums import EntityScope
    from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
    from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts
    from cse_financial_etl.v2.resolution.resolver import source_admission_failure
    from cse_financial_etl.v2.taxonomy.registry import load_registry

    pdf = Path(cohort_item["abs_path"])
    metric = item["metric_code"]
    want_val = _dec(item.get("normalized_value") or item.get("raw_text"))
    want_ent = item.get("entity_scope") or ""
    period = date.fromisoformat(item["period_end"])
    registry = load_registry()

    def classify(result, label: str) -> dict:
        cands = [
            c
            for c in result.candidates
            if c.concept
            and c.concept.metric_code == metric
            and _dec(str(c.raw_value) if c.raw_value is not None else "") == want_val
        ]
        facts = [
            f
            for f in result.source_facts
            if f.metric_code == metric and _dec(str(f.normalized_value)) == want_val
        ]
        if not cands and not facts:
            # any same metric value near raw_text?
            obs = collect_v1_source_observations(
                pdf,
                filing_version_id="probe",
                filing_id=str(cohort_item.get("symbol") or ""),
            )
            value_hits = [o for o in obs if _dec(str(o.raw_value)) == want_val]
            if not value_hits:
                return {"engine": label, "first_loss": "MISSING_CELL_OR_VALUE"}
            disc = observations_to_discovery_candidates(tuple(value_hits[:5]))
            fails = [
                None
                if source_admission_failure(c, registry=registry) is None
                else source_admission_failure(c, registry=registry).value
                for c in disc
            ]
            return {
                "engine": label,
                "first_loss": fails[0] or "OBSERVED_BUT_NOT_IN_PIPELINE_CANDIDATES",
                "observation_hits": len(value_hits),
            }
        if cands and not facts:
            fail = source_admission_failure(cands[0], registry=registry)
            return {
                "engine": label,
                "first_loss": fail.value if fail else "ADMISSION_OK_BUT_NO_SOURCEFACT",
                "candidate_reasons": list(cands[0].reason_codes or ())[:8],
            }
        # have facts
        elig = [f for f in facts if f.publication_status.value == "ELIGIBLE"]
        if not elig:
            return {
                "engine": label,
                "first_loss": "WITHHELD_"
                + "+".join((facts[0].reason_codes or ("UNKNOWN",))[:3]),
            }
        ent = None
        for name in ("COMPANY", "GROUP", "BANK"):
            try:
                ent = EntityScope[name]
            except KeyError:
                continue
            if want_ent and name != want_ent:
                continue
            sel = select_pipeline_facts(result.source_facts, period_end=period, expected_entity=ent)
            if any(f.metric_code == metric and _dec(str(f.normalized_value)) == want_val for f in sel):
                return {"engine": label, "first_loss": "SELECTED_OK"}
        return {"engine": label, "first_loss": "ELIGIBLE_NOT_SELECTED"}

    v2 = run_pdf_pipeline(
        pdf,
        issuer_id=str(cohort_item.get("symbol") or ""),
        filing_version_id="v2-probe",
        issuer_name=str(cohort_item.get("legal_name") or ""),
        v1_source_observations=False,
    )
    as_ = run_pdf_pipeline(
        pdf,
        issuer_id=str(cohort_item.get("symbol") or ""),
        filing_version_id="as-probe",
        issuer_name=str(cohort_item.get("legal_name") or ""),
        v1_source_observations=True,
    )
    return {"v1_only_key": item, "v2": classify(v2, "v2"), "assisted": classify(as_, "assisted")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=int, default=24, help="V1-only keys to live-probe")
    parser.add_argument("--review", type=int, default=40, help="stratified review queue size")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    v1 = _load(BASE / "ledger_v1.csv")
    v2 = _load(BASE / "ledger_v2.csv")
    assisted = _load(BASE / "ledger_v1_assisted_v2.csv")
    cohort = json.loads((BASE / "pinned_cohort.json").read_text(encoding="utf-8"))
    by_sha = {f["pdf_sha256"]: f for f in cohort["filings"]}

    v1_keys = {_key(r): r for r in v1 if r.get("metric_code") in TARGET}
    v2_elig = {
        _key(r): r
        for r in v2
        if r.get("metric_code") in TARGET and r.get("publication_status") == "ELIGIBLE"
    }
    as_elig = {
        _key(r): r
        for r in assisted
        if r.get("metric_code") in TARGET and r.get("publication_status") == "ELIGIBLE"
    }
    v2_sel = {_key(r): r for r in v2 if str(r.get("draft_selected")).lower() == "true"}
    as_sel = {_key(r): r for r in assisted if str(r.get("draft_selected")).lower() == "true"}

    # Soft identity for V1 vs V2 without requiring value match when V1 normalized empty
    v1_soft = defaultdict(list)
    for r in v1:
        if r.get("metric_code") in TARGET:
            v1_soft[_soft_key(r)].append(r)
    v2_soft_elig = defaultdict(list)
    for r in v2:
        if r.get("metric_code") in TARGET and r.get("publication_status") == "ELIGIBLE":
            v2_soft_elig[_soft_key(r)].append(r)

    both_same = 0
    both_conflict = 0
    v1_only_soft = []
    for sk, rows in v1_soft.items():
        peers = v2_soft_elig.get(sk) or []
        if not peers:
            v1_only_soft.extend(rows)
            continue
        v1_vals = {_dec(r.get("normalized_value") or r.get("raw_text")) for r in rows}
        v2_vals = {_dec(r.get("normalized_value")) for r in peers}
        if v1_vals & v2_vals:
            both_same += 1
        else:
            both_conflict += 1

    funnel_v2 = selection_funnel([r for r in v2 if r.get("metric_code") in TARGET])
    funnel_as = selection_funnel([r for r in assisted if r.get("metric_code") in TARGET])

    v1_only_sample = stratify_sample(v1_only_soft, n=args.review)
    new_as = [as_sel[k] for k in as_sel.keys() - v2_sel.keys()]
    lost_as = [v2_sel[k] for k in v2_sel.keys() - as_sel.keys()]
    review_queue = {
        "v1_only_stratified": v1_only_sample,
        "assisted_new_selected": stratify_sample(new_as, n=min(20, len(new_as))),
        "assisted_lost_selected": stratify_sample(lost_as, n=min(20, len(lost_as))),
        "adjudication_status": "PENDING_PDF_REVIEW",
        "note": "These are engine differentials, not yet source-verified correct facts.",
    }
    (OUT / "source_review_queue.json").write_text(
        json.dumps(review_queue, indent=2, default=str), encoding="utf-8"
    )

    probes = []
    probe_rows = stratify_sample(v1_only_soft, n=args.probe, seed=7)
    for row in probe_rows:
        sha = row.get("pdf_sha256")
        item = by_sha.get(sha or "")
        if item is None or not Path(item["abs_path"]).is_file():
            probes.append({"v1_only_key": row, "error": "missing_pdf"})
            continue
        print(
            f"probe {row.get('issuer_dir')} {row.get('metric_code')} {row.get('entity_scope')}…",
            flush=True,
        )
        try:
            probes.append(probe_first_loss(row, item))
        except Exception as exc:  # noqa: BLE001 — investigation must continue
            probes.append({"v1_only_key": row, "error": str(exc)})

    loss_v2 = Counter(
        (p.get("v2") or {}).get("first_loss") or p.get("error") or "UNKNOWN" for p in probes
    )
    loss_as = Counter(
        (p.get("assisted") or {}).get("first_loss") or p.get("error") or "UNKNOWN" for p in probes
    )
    (OUT / "v1_only_first_loss_probes.json").write_text(
        json.dumps({"probes": probes, "v2_counts": dict(loss_v2), "assisted_counts": dict(loss_as)}, indent=2, default=str),
        encoding="utf-8",
    )

    summary = {
        "id": "phase-a-source-valid-gap",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "baseline_run": "same_input_2026-09-09",
        "pinned_filings": cohort.get("filings_selected"),
        "counts": {
            "v1_target_rows": len(v1_keys),
            "v2_eligible_hard_keys": len(v2_elig),
            "assisted_eligible_hard_keys": len(as_elig),
            "v2_draft_selected_hard_keys": len(v2_sel),
            "assisted_draft_selected_hard_keys": len(as_sel),
            "v1_only_soft_slots": len(v1_only_soft),
            "soft_both_same_value": both_same,
            "soft_both_conflict_value": both_conflict,
            "assisted_new_selected": len(new_as),
            "assisted_lost_selected": len(lost_as),
        },
        "selection_funnel_v2": funnel_v2,
        "selection_funnel_assisted": funnel_as,
        "v1_only_probe_first_loss_v2": dict(loss_v2.most_common()),
        "v1_only_probe_first_loss_assisted": dict(loss_as.most_common()),
        "decision_gate_note": (
            "If probe first_loss is dominated by MISSING_CELL_OR_VALUE / CONCEPT / ENTITY / PERIOD, "
            "prioritize physical reader/context. If ELIGIBLE_NOT_SELECTED / WITHHELD_CONFLICTING, "
            "prioritize admission/selection bridge."
        ),
    }
    (OUT / "phase_a_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md = f"""# Source-valid gap and selection waterfall (Phase A)

**Plan:** `docs/v2/CSE_V2_FINAL_AGENT_EXECUTION_PLAN.md`  
**Baseline freeze:** `reports/v1_v2_same_input/baseline_freeze_2026-09-20_plus3/`  
**Cohort:** pinned 829 (`same_input_2026-09-09`)  
**Status:** quant + probe complete; PDF adjudication of review queue still **PENDING** (engine keys ≠ source truth).

## Frozen baseline KPIs (do not rewrite)

| | V2-only | Assisted | Net |
|---|---:|---:|---:|
| TARGET draft-selected | 2,816 | 2,819 | **+3** |
| E13 total draft-publishable (reference) | 3,854 | — | not same definition |
| Governance floor | — | 8,924 | separate gate |

## Selection funnel (TARGET rows on ledgers)

### V2-only
{json.dumps(funnel_v2, indent=2)}

### Assisted
{json.dumps(funnel_as, indent=2)}

~9.8k ELIGIBLE rows collapse to ~2.8k selected primarily via CURRENT + duration∈{{null,3}} + expected-entity unique-by-metric — **selection policy**, not solely extraction failure.

## Soft-key differential (metric/entity/period/dur/cmp; value compared when both present)

| Class | Count |
|---|---:|
| V1 soft slots with no V2 ELIGIBLE peer | **{len(v1_only_soft)}** |
| Soft slots both present, shared value | {both_same} |
| Soft slots both present, conflicting values | {both_conflict} |
| Assisted newly selected hard keys vs V2 | {len(new_as)} |
| Assisted lost selected hard keys vs V2 | {len(lost_as)} |

## V1-only first-loss probe (n={len(probes)}, live pipeline)

### V2-only
{json.dumps(dict(loss_v2.most_common()), indent=2)}

### Assisted
{json.dumps(dict(loss_as.most_common()), indent=2)}

## Decision gate

See probe distribution. Prefer the dominant *first causal loss* among **PDF-verified** V1-only facts (review queue still pending). Do not treat all {len(v1_only_soft)} V1-only soft slots as correct recoverable facts.

## Artifacts

- `phase_a_summary.json`
- `source_review_queue.json` (adjudication_status=PENDING_PDF_REVIEW)
- `v1_only_first_loss_probes.json`
- Baseline checksums: `../baseline_freeze_2026-09-20_plus3/BASELINE_FREEZE_MANIFEST.json`

## Production

V1 remains default. Not READY FOR OFFICIAL DECISION.
"""
    (OUT / "SOURCE_VALID_GAP_AND_SELECTION_WATERFALL.md").write_text(md, encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
