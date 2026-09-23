#!/usr/bin/env python3
"""Score the synthetic V2 golden corpus. Does not claim institutional CSE gold."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cse_financial_etl.v2.contracts.enums import PublicationStatus, ValidationStatus
from cse_financial_etl.v2.diagnostics.golden import (
    aggregate_golden_reports,
    evaluate_golden_gates,
    score_golden,
)
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parent.parent, *here.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit("could not locate project root (pyproject.toml)")


def main(argv: list[str] | None = None) -> int:
    del argv
    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tests.v2.golden.corpus import load_synthetic_corpus

    corpus = load_synthetic_corpus()
    reports = []
    negatives = 0
    for case in corpus:
        result = run_filing_pipeline(
            case.document,
            issuer_id=case.issuer_id,
            expected_entity_scope=case.expected_entity_scope,
            accounting_regime=case.accounting_regime,
        )
        facts = result.source_facts
        policy_facts = (
            result.production_selected_source
            if case.expected_entity_scope is not None
            else facts
        )
        published = {
            fact.metric_code
            for fact in policy_facts
            if fact.publication_status is not PublicationStatus.WITHHELD
            and fact.validation_status is not ValidationStatus.FAILED
        }
        leaked = sorted(set(case.must_not_publish) & published)
        if leaked:
            print(json.dumps({"case_id": case.case_id, "leaked_metrics": leaked}))
            return 1
        if case.expected:
            reports.append(score_golden(case.expected, facts))
        else:
            negatives += 1
    combined = aggregate_golden_reports(tuple(reports))
    gates = evaluate_golden_gates(combined)
    payload = {
        "case_count": len(corpus),
        "negative_cases": negatives,
        "report": combined.model_dump(mode="json"),
        "gates": gates.model_dump(mode="json"),
        "note": "synthetic adjudicated fixtures; not the institutional 25-40 CSE filing corpus",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if gates.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
