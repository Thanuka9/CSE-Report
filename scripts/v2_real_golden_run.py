#!/usr/bin/env python3
"""Score V2 against available V1-adjudicated CSE filings. Does not claim §37 institutional gold."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cse_financial_etl.v2.diagnostics.golden import (
    aggregate_golden_reports,
    evaluate_golden_gates,
    score_golden,
)
from cse_financial_etl.v2.diagnostics.real_filings import load_gold_lock, load_real_filing_cases
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root (pyproject.toml)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument(
        "--unlocked", action="store_true", help="Score JSON order instead of the locked 25-40 set"
    )
    args = parser.parse_args(argv)
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    lock = load_gold_lock(root=root)
    cases = load_real_filing_cases(limit=args.limit, root=root, locked=not args.unlocked)
    reports = []
    case_rows = []
    for case in cases:
        _statements, facts, _derived, _metrics = run_pdf_pipeline(
            case.pdf_path,
            issuer_id=case.issuer_id,
            filing_version_id=case.case_id,
            expected_entity_scope=case.entity_scope,
            target_period_end=case.period_end,
            issuer_name=case.issuer_name,
            issuer_type=case.issuer_type,
        )
        report = score_golden(case.expected, facts)
        reports.append(report)
        case_rows.append(
            {
                "case_id": case.case_id,
                "pdf": str(case.pdf_path),
                "true_positives": report.true_positives,
                "expected_count": report.expected_count,
                "critical_wrong_populated": report.critical_wrong_populated,
                "source_reported_recall": report.source_reported_recall,
                "verification_status": case.verification_status,
                "issuer_type": case.issuer_type,
            }
        )
    combined = aggregate_golden_reports(tuple(reports)) if reports else None
    gates = evaluate_golden_gates(combined) if combined is not None else None
    payload = {
        "case_count": len(cases),
        "lock_id": lock.lock_id,
        "report": combined.model_dump(mode="json") if combined is not None else None,
        "gates": gates.model_dump(mode="json") if gates is not None else None,
        "cases": case_rows,
        "note": lock.note,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if cases else 1


if __name__ == "__main__":
    raise SystemExit(main())
