"""Governed production entrypoint for the CSE quarterly ETL.

The stable extraction/compiler remains the core engine. Production-specific controls are
applied around it, R4 regulatory/semantic policy is applied before acceptance, and gold
is activated only after the complete candidate generation passes those gates.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from cse_financial_etl.orchestration.resilient_pipeline import run_resilient_pipeline
from cse_financial_etl.production.r4_hardening import (
    apply_r4_hardening,
    r4_runtime_guards,
)
from cse_financial_etl.production.runtime import (
    build_issuer_master,
    production_runtime,
    promote_staged_run,
    relabel_workbook_leverage,
    write_metric_definitions,
)
from cse_financial_etl.reporting.excel import generate_excel
from cse_financial_etl.validation.universe_acceptance import evaluate_universe_acceptance


def _rolling_periods(as_of: date) -> tuple[date, ...]:
    quarter_ends = [
        date(year, month, 31 if month in {3, 12} else 30)
        for year in range(as_of.year - 2, as_of.year + 1)
        for month in (3, 6, 9, 12)
    ]
    completed = [period for period in quarter_ends if period <= as_of]
    return tuple(completed[-3:])


def _parse_periods(value: str | None, as_of: date) -> tuple[date, ...]:
    if not value:
        return _rolling_periods(as_of)
    parsed = tuple(date.fromisoformat(item.strip()) for item in value.split(",") if item.strip())
    if not parsed:
        raise ValueError("At least one period is required")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the CSE ETL with production source, R4 semantic, acceptance and promotion controls."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--as-of", required=True, help="Market observation date YYYY-MM-DD")
    parser.add_argument("--periods", help="Optional comma-separated quarter ends")
    parser.add_argument("--process-timeout-seconds", type=float, default=480.0)
    parser.add_argument("--api-workers", type=int, default=24)
    parser.add_argument("--download-workers", type=int, default=12)
    parser.add_argument("--extraction-workers", type=int, default=8)
    parser.add_argument("--issuer-limit", type=int)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-excel", action="store_true")
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--tunnel-b-always", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    as_of = date.fromisoformat(args.as_of)
    periods = _parse_periods(args.periods, as_of)

    with production_runtime(root, as_of_date=as_of, offline=args.offline) as capture:
        # The governed workbook must never be built from pre-R4 rows.  The core pipeline
        # therefore always skips Excel here; a requested workbook is generated only after
        # R4 has rewritten the public CSVs and acceptance has been evaluated below.
        with r4_runtime_guards(root, as_of):
            result = run_resilient_pipeline(
                root,
                as_of_date=as_of,
                periods=periods,
                process_timeout_seconds=args.process_timeout_seconds,
                api_workers=args.api_workers,
                download_workers=args.download_workers,
                extraction_workers=args.extraction_workers,
                issuer_limit=args.issuer_limit,
                offline=args.offline,
                skip_excel=True,
                compile_statements=not args.no_compile,
                run_tunnel_b_always=args.tunnel_b_always,
            )

        issuer_master = build_issuer_master(root, as_of)
        metric_definitions = write_metric_definitions(root, as_of)

        if capture.repository is None or capture.staging is None:
            raise RuntimeError("Production pipeline did not produce a staged candidate generation")
        r4_summary = apply_r4_hardening(
            root,
            as_of,
            periods,
            capture.repository,
            run_status=capture.status or "VALIDATION_REQUIRED",
            statistics=capture.statistics,
        )

        acceptance_path = root / "outputs" / f"universe_acceptance_{as_of.isoformat()}.json"
        acceptance = evaluate_universe_acceptance(
            manifest_path=root / "outputs" / "manifests" / f"run_manifest_{as_of.isoformat()}.json",
            review_path=root / "outputs" / f"review_queue_{as_of.isoformat()}.csv",
            facts_path=root / "outputs" / f"normalized_facts_{as_of.isoformat()}.csv",
            errors_path=root / "outputs" / f"pipeline_errors_{as_of.isoformat()}.json",
            baseline_path=root / "configs" / "coverage_baseline.yml",
        )
        promotion = promote_staged_run(
            capture,
            acceptance,
            release_mode=str(result.get("release_mode") or "OFFICIAL"),
        )
        acceptance["production_runtime"] = {
            "source_mode": "OFFLINE_REPLAY" if args.offline else "LIVE_OBSERVATION",
            "issuer_master": str(issuer_master),
            "metric_definitions": str(metric_definitions),
            "quarter_model": "REPORTED_THREE_MONTH_QUARTERS_ONLY",
            "r4_hardening": r4_summary,
            "database_required": False,
            "xbrl_enabled": False,
            "gold_promotion": promotion,
        }
        acceptance_path.write_text(json.dumps(acceptance, indent=2), encoding="utf-8")

        if not args.skip_excel:
            workbook_path = generate_excel(
                root,
                as_of,
                periods,
                str(result.get("run_id") or "UNKNOWN"),
            )
            relabel_workbook_leverage(workbook_path)
            result["workbook"] = str(workbook_path)

    payload = {
        **result,
        "r4_hardening": r4_summary,
        "universe_acceptance": acceptance,
        "gold_promotion": promotion,
    }
    print(json.dumps(payload, indent=2, default=str))
    if acceptance["acceptance"] == "ENGINEERING_FAILURES_PRESENT":
        return 1
    if str(result.get("release_mode") or "").upper() == "OFFICIAL" and not promotion.get("promoted"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
