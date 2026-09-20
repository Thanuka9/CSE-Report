"""Reproduce documented wrong bridge selections (investigation)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline
from cse_financial_etl.v2.resolution.production_selection import select_pipeline_facts

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "reports" / "v1_v2_same_input" / "same_input_2026-09-09"

CASES = [
    ("JAT_HOLDINGS_PLC", "2025-12-31", "TOP_LINE", EntityScope.COMPANY),
    ("HAYLEYS_PLC", "2026-03-31", "TOP_LINE", EntityScope.COMPANY),
    ("HOTEL_SIGIRIYA_PLC", "2026-06-30", "EPS_BASIC", EntityScope.COMPANY),
]


def main() -> None:
    cohort = json.loads((RUN / "pinned_cohort.json").read_text(encoding="utf-8"))
    by = {(f["issuer_dir"], f["period_end"]): f for f in cohort["filings"]}
    for issuer, period, metric, entity in CASES:
        item = by[(issuer, period)]
        pdf = Path(item["abs_path"])
        print("===", issuer, period, metric, entity.value)
        for mode, flag in (("v2", False), ("as", True)):
            result = run_pdf_pipeline(
                pdf,
                issuer_id=item["symbol"],
                filing_version_id=f"{mode}-{period}",
                issuer_name=str(item.get("legal_name") or ""),
                v1_source_observations=flag,
            )
            pe = date.fromisoformat(period)
            selected = select_pipeline_facts(
                result.source_facts, period_end=pe, expected_entity=entity
            )
            hits = [f for f in selected if f.metric_code == metric]
            if not hits:
                # show eligible for metric
                elig = [
                    f
                    for f in result.source_facts
                    if f.metric_code == metric and f.entity_scope is entity
                ]
                print(
                    f"  {mode}: NOT SELECTED; eligible_count={len(elig)} "
                    f"values={[str(f.normalized_value) for f in elig[:8]]}"
                )
                continue
            fact = hits[0]
            print(
                f"  {mode}: selected={fact.normalized_value} raw={fact.raw_value} "
                f"page={fact.source_ref.page_number} "
                f"text={(fact.source_ref.raw_text or '')[:100]!r} "
                f"reasons={fact.reason_codes[:8]}"
            )


if __name__ == "__main__":
    main()
