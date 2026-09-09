from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from cse_financial_etl.orchestration.resilient_pipeline import run_resilient_pipeline


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
        description="Run the CSE ETL with per-PDF hard cancellation and resumable caches."
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--as-of", required=True, help="Market snapshot date YYYY-MM-DD")
    parser.add_argument("--periods", help="Optional comma-separated period ends")
    parser.add_argument("--process-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--api-workers", type=int, default=24)
    parser.add_argument("--download-workers", type=int, default=20)
    parser.add_argument("--extraction-workers", type=int, default=8)
    parser.add_argument("--issuer-limit", type=int)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--skip-excel", action="store_true")
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--tunnel-b-always", action="store_true")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of)
    periods = _parse_periods(args.periods, as_of)
    result = run_resilient_pipeline(
        args.project_root,
        as_of_date=as_of,
        periods=periods,
        process_timeout_seconds=args.process_timeout_seconds,
        api_workers=args.api_workers,
        download_workers=args.download_workers,
        extraction_workers=args.extraction_workers,
        issuer_limit=args.issuer_limit,
        offline=args.offline,
        skip_excel=args.skip_excel,
        compile_statements=not args.no_compile,
        run_tunnel_b_always=args.tunnel_b_always,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
