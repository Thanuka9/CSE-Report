"""Offline accuracy / coverage evaluation harness (sections 48-49).

Does not fake human adjudication. Runs measurable offline strata against local
filings, golden fixtures, and compiler publication stats.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import extract_filing, facts_by_code
from cse_financial_etl.storage.stage_cache import atomic_write_text

TRACKED_METRICS: tuple[str, ...] = (
    "document_reconstruction",
    "statement_classification",
    "header_column_ownership",
    "entity",
    "duration",
    "current_comparative",
    "unit",
    "semantic_row_label",
    "numeric_exact",
    "wrong_populated_cell",
    "core_metric_coverage",
    "recovery_success",
    "tunnel_agreement",
    "terminal_unresolved",
)


@dataclass(frozen=True, slots=True)
class EvalCase:
    issuer_name: str
    symbol: str
    period_end: date
    pdf: Path
    expected: dict[str, str] | None = None
    stratum: str = "local_lake"


def load_cases_from_golden(project_root: Path) -> list[EvalCase]:
    fixture = project_root / "tests" / "fixtures" / "golden_financial_facts.json"
    if not fixture.exists():
        return []
    rows = json.loads(fixture.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for row in rows:
        pdf = project_root / str(row.get("pdf") or "")
        if not pdf.exists():
            continue
        cases.append(
            EvalCase(
                issuer_name=str(row["issuer_name"]),
                symbol=str(row["symbol"]),
                period_end=date.fromisoformat(str(row["period_end"])),
                pdf=pdf,
                expected={k: str(v) for k, v in (row.get("facts") or {}).items()},
                stratum=str(row.get("verification_status") or "PIPELINE_SEEDED"),
            )
        )
    return cases


def evaluate_case(case: EvalCase, *, compile_statements: bool = False) -> dict[str, Any]:
    facts = extract_filing(
        case.pdf,
        case.issuer_name,
        case.symbol,
        case.period_end,
        ocr_enabled=False,
        compile_statements=compile_statements,
    )
    by_code = facts_by_code(facts)
    publication_paths: Counter[str] = Counter()
    candidate_origins: Counter[str] = Counter()
    explicit_fallbacks = 0
    extracted = 0
    for fact in facts:
        evidence: dict[str, Any] = {}
        if fact.evidence_json:
            try:
                evidence = json.loads(fact.evidence_json)
            except json.JSONDecodeError:
                evidence = {}
        publication_paths[str(evidence.get("publication_path") or "unknown")] += 1
        candidate_origins[str(evidence.get("candidate_origin") or "unknown")] += 1
        if evidence.get("publication_path") == "explicit_layout_fallback":
            explicit_fallbacks += 1
        if fact.status in {"EXTRACTED", "EXTRACTED_DERIVED"}:
            extracted += 1

    numeric_pass = 0
    numeric_fail = 0
    if case.expected:
        for code, expected in case.expected.items():
            found_fact = by_code.get(code)
            actual = (
                str(found_fact.normalized_value)
                if found_fact is not None and found_fact.normalized_value is not None
                else None
            )
            if actual is None:
                numeric_fail += 1
            elif _decimal_equal(actual, expected):
                numeric_pass += 1
            else:
                numeric_fail += 1

    return {
        "issuer": case.issuer_name,
        "symbol": case.symbol,
        "period_end": case.period_end.isoformat(),
        "stratum": case.stratum,
        "fact_count": len(facts),
        "extracted_count": extracted,
        "publication_paths": dict(publication_paths),
        "candidate_origins": dict(candidate_origins),
        "explicit_fallback_count": explicit_fallbacks,
        "numeric_pass": numeric_pass,
        "numeric_fail": numeric_fail,
        "compiler_publish_ok": publication_paths.get("statement_compiler", 0) > 0,
        "silent_layout_publish": publication_paths.get("unknown", 0) > 0
        and publication_paths.get("statement_compiler", 0) == 0
        and publication_paths.get("explicit_layout_fallback", 0) == 0,
    }


def run_offline_eval(
    project_root: Path,
    *,
    cases: list[EvalCase] | None = None,
    compile_statements: bool = False,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    selected = cases if cases is not None else load_cases_from_golden(project_root)
    results = [
        evaluate_case(case, compile_statements=compile_statements) for case in selected
    ]
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_stratum[str(row["stratum"])].append(row)

    summary = {
        "tracked_metrics": list(TRACKED_METRICS),
        "case_count": len(results),
        "compiler_publish_cases": sum(1 for r in results if r["compiler_publish_ok"]),
        "silent_layout_publish_cases": sum(1 for r in results if r["silent_layout_publish"]),
        "explicit_fallback_facts": sum(int(r["explicit_fallback_count"]) for r in results),
        "numeric_pass": sum(int(r["numeric_pass"]) for r in results),
        "numeric_fail": sum(int(r["numeric_fail"]) for r in results),
        "by_stratum": {
            stratum: {
                "cases": len(rows),
                "numeric_pass": sum(int(r["numeric_pass"]) for r in rows),
                "numeric_fail": sum(int(r["numeric_fail"]) for r in rows),
            }
            for stratum, rows in sorted(by_stratum.items())
        },
        "results": results,
        "release_gates_note": (
            "Official §49 gates requiring independent human adjudication of unique "
            "published source facts are EXTERNAL and not claimed by this offline harness."
        ),
        "cases": [
            {
                "issuer_name": c.issuer_name,
                "symbol": c.symbol,
                "period_end": c.period_end.isoformat(),
                "pdf": str(c.pdf),
                "stratum": c.stratum,
            }
            for c in selected
        ],
    }
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            output_dir / "offline_eval_summary.json",
            json.dumps(summary, indent=2, default=str),
        )
    return summary


def _decimal_equal(actual: str, expected: str) -> bool:
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(actual) == Decimal(expected)
    except (InvalidOperation, ValueError):
        return actual == expected
