"""Instrument V1-observation → SourceFact admission on one pinned PDF (investigation only).

Does not change extraction, floors, or run the full universe.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "v1_v2_same_input" / "same_input_2026-09-09"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer-dir", default="ABANS_ELECTRICALS_PLC")
    parser.add_argument("--period-end", default="2025-12-31")
    parser.add_argument("--value", default="1928502029", help="Raw numeric to trace")
    args = parser.parse_args()

    from cse_financial_etl.v2.challenger.observation_union import (
        observations_to_discovery_candidates,
    )
    from cse_financial_etl.v2.challenger.v1_source_observations import (
        collect_v1_source_observations,
    )
    from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
    from cse_financial_etl.v2.resolution.resolver import source_admission_failure
    from cse_financial_etl.v2.taxonomy.registry import load_registry

    cohort = json.loads((RUN / "pinned_cohort.json").read_text(encoding="utf-8"))
    item = next(
        f
        for f in cohort["filings"]
        if f["issuer_dir"] == args.issuer_dir and f["period_end"] == args.period_end
    )
    pdf = Path(item["abs_path"])
    target = Decimal(args.value)
    symbol = item.get("symbol") or item["issuer_dir"]

    obs = collect_v1_source_observations(
        pdf, filing_version_id="admission-trace", filing_id=str(symbol)
    )
    cands = observations_to_discovery_candidates(obs)
    reg = load_registry()
    adm = Counter(
        None if source_admission_failure(c, registry=reg) is None else source_admission_failure(c, registry=reg).value
        for c in cands
    )

    assisted = run_pdf_pipeline(
        pdf,
        issuer_id=str(symbol),
        filing_version_id=f"{symbol}-{args.period_end}",
        issuer_name=str(item.get("legal_name") or ""),
        issuer_type=str(item.get("issuer_type") or ""),
        v1_source_observations=True,
    )
    v1_union = [
        c for c in assisted.candidates if "V1_OBSERVATION_UNION" in (c.reason_codes or ())
    ]
    union_adm = Counter(
        None
        if source_admission_failure(c, registry=reg) is None
        else source_admission_failure(c, registry=reg).value
        for c in v1_union
    )
    value_hits = [c for c in v1_union if c.raw_value == target]

    report = {
        "pdf": item.get("local_path"),
        "observations": len(obs),
        "all_discovery_only": all(o.discovery_only for o in obs),
        "entity_period_unit_filled": {
            "entity": sum(1 for o in obs if o.entity_scope is not None),
            "period": sum(1 for o in obs if o.period_end is not None),
            "unit": sum(1 for o in obs if o.unit_dimension is not None),
        },
        "discovery_candidate_admission": dict(adm),
        "assisted_v1_union_count": len(v1_union),
        "assisted_v1_union_admission": dict(union_adm),
        "source_facts": len(assisted.source_facts),
        "eligible": sum(
            1 for f in assisted.source_facts if f.publication_status.value == "ELIGIBLE"
        ),
        "v1obs_fact_ids": sum(1 for f in assisted.source_facts if "v1obs" in f.fact_id),
        "traced_value": str(target),
        "traced_value_adapter_hits": [
            {
                "concept": None if c.concept is None else c.concept.metric_code,
                "admission": None
                if source_admission_failure(c, registry=reg) is None
                else source_admission_failure(c, registry=reg).value,
                "reason_codes": list(c.reason_codes or ()),
                "page": c.source_ref.page_number,
                "bbox": list(c.source_ref.bbox) if c.source_ref.bbox else None,
                "raw_text": c.source_ref.raw_text,
            }
            for c in value_hits
        ],
        "note": (
            "DISCOVERY_ONLY is stamped at observation birth; resolver rejects via "
            "ordinary CONCEPT/ENTITY/PERIOD/UNIT gates. No verify-and-promote path exists."
        ),
    }
    out = RUN / "adapter_admission_trace.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
