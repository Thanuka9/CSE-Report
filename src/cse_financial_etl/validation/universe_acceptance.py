"""Production acceptance for a complete CSE universe run.

This is deliberately stricter than the pipeline's per-filing validation.  It owns the
universe-level contract: known timeout quarantine, aggregate and decomposed coverage,
and separation of engineering failures from independent human-proof requirements.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from cse_financial_etl.config import infer_issuer_type
from cse_financial_etl.validation.acceptance import is_publishable_fact

EXTERNAL_PROOF_GATES = {
    "GOLD_SAMPLE_INCOMPLETE",
    "GOLD_ISSUER_SAMPLE_INCOMPLETE",
}
TIMEOUT_PATTERN = re.compile(
    r"^PDF/OCR worker exceeded \d+(?:\.\d+)?s and its process tree was terminated$"
)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return parsed


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list):
        raise ValueError(f"Expected a JSON list in {path}")
    return [row for row in parsed if isinstance(row, dict)]


def _draft_publishable_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            dict(row)
            for row in csv.DictReader(handle)
            if is_publishable_fact(row, release_mode="DRAFT")
        ]


def _timeout_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("issuer_name") or "").strip().casefold(),
        str(row.get("symbol") or "").strip().upper(),
        str(row.get("period_end") or "").strip(),
    )


def _timeout_allowlist(baseline: dict[str, Any]) -> set[tuple[str, str, str]]:
    allowed: set[tuple[str, str, str]] = set()
    raw = baseline.get("quarantined_extraction_timeouts") or []
    if not isinstance(raw, list):
        raise ValueError("quarantined_extraction_timeouts must be a list")
    for row in raw:
        if not isinstance(row, dict):
            continue
        identity = _timeout_identity(row)
        if all(identity):
            allowed.add(identity)
    return allowed


def _classify_pipeline_errors(
    errors: list[dict[str, Any]],
    *,
    expected_count: int,
    baseline: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Quarantine only explicitly approved pathological filings.

    A newly timing-out filing is an engineering failure even when the total number of
    timeouts remains below the historical limit.  This prevents a new OCR/parser
    regression from hiding behind an old universe-wide count allowance.
    """

    maximum = max(0, int(baseline.get("max_quarantined_extraction_timeouts") or 0))
    allowlist = _timeout_allowlist(baseline)
    quarantined: list[dict[str, Any]] = []
    unhandled: list[dict[str, Any]] = []
    for row in errors:
        stage = str(row.get("stage") or "")
        error = str(row.get("error") or "")
        exact_timeout = stage == "EXTRACTION" and bool(TIMEOUT_PATTERN.fullmatch(error))
        if exact_timeout and _timeout_identity(row) in allowlist:
            quarantined.append({**row, "classification": "KNOWN_TIMEOUT_QUARANTINE"})
        elif exact_timeout:
            unhandled.append({**row, "classification": "UNEXPECTED_EXTRACTION_TIMEOUT"})
        else:
            unhandled.append(row)

    if len(quarantined) > maximum:
        overflow = quarantined[maximum:]
        quarantined = quarantined[:maximum]
        unhandled.extend(
            {
                **row,
                "classification": "QUARANTINE_LIMIT_EXCEEDED",
                "quarantine_limit": maximum,
            }
            for row in overflow
        )

    if expected_count != len(errors):
        unhandled.append(
            {
                "stage": "ACCEPTANCE",
                "error": (
                    "pipeline_error_count mismatch: "
                    f"manifest={expected_count} artifact={len(errors)}"
                ),
                "classification": "PIPELINE_ERROR_EVIDENCE_MISMATCH",
            }
        )
    return quarantined, unhandled


def _coverage_summary(
    rows: list[dict[str, str]], baseline: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_metric = Counter(str(row.get("metric_code") or "") for row in rows)
    by_sector_metric = Counter(
        (infer_issuer_type(str(row.get("issuer_name") or "")), str(row.get("metric_code") or ""))
        for row in rows
    )
    regressions: list[dict[str, Any]] = []

    metric_floors = baseline.get("min_publishable_by_metric") or {}
    if not isinstance(metric_floors, dict):
        raise ValueError("min_publishable_by_metric must be a mapping")
    for metric, floor_raw in metric_floors.items():
        floor = int(floor_raw)
        actual = int(by_metric[str(metric)])
        if actual < floor:
            regressions.append(
                {
                    "code": "METRIC_COVERAGE_REGRESSION",
                    "metric_code": str(metric),
                    "actual": actual,
                    "floor": floor,
                }
            )

    sector_floors = baseline.get("min_publishable_by_sector_metric") or {}
    if not isinstance(sector_floors, dict):
        raise ValueError("min_publishable_by_sector_metric must be a mapping")
    for sector, metrics in sector_floors.items():
        if not isinstance(metrics, dict):
            raise ValueError(f"sector coverage floor for {sector} must be a mapping")
        for metric, floor_raw in metrics.items():
            floor = int(floor_raw)
            actual = int(by_sector_metric[(str(sector), str(metric))])
            if actual < floor:
                regressions.append(
                    {
                        "code": "SECTOR_METRIC_COVERAGE_REGRESSION",
                        "issuer_type": str(sector),
                        "metric_code": str(metric),
                        "actual": actual,
                        "floor": floor,
                    }
                )

    summary = {
        "draft_publishable_count": len(rows),
        "by_metric": dict(sorted(by_metric.items())),
        "by_sector_metric": {
            sector: {
                metric: int(by_sector_metric[(sector, metric)])
                for metric in sorted({m for s, m in by_sector_metric if s == sector})
            }
            for sector in sorted({s for s, _m in by_sector_metric})
        },
    }
    return summary, regressions


def evaluate_universe_acceptance(
    *,
    manifest_path: Path,
    review_path: Path,
    facts_path: Path,
    errors_path: Path,
    baseline_path: Path,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    baseline = _load_yaml(baseline_path)
    gates = list((manifest.get("production_gates") or {}).get("hits") or [])
    engineering_gates = [row for row in gates if row.get("code") not in EXTERNAL_PROOF_GATES]
    proof_gates = [row for row in gates if row.get("code") in EXTERNAL_PROOF_GATES]

    expected_error_count = int(manifest.get("pipeline_error_count") or 0)
    pipeline_errors = _load_json_list(errors_path)
    quarantined_errors, unhandled_errors = _classify_pipeline_errors(
        pipeline_errors,
        expected_count=expected_error_count,
        baseline=baseline,
    )

    review_counts: Counter[str] = Counter()
    if review_path.exists():
        with review_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                review_counts[str(row.get("reason") or "UNKNOWN")] += 1

    publishable_rows = _draft_publishable_rows(facts_path)
    coverage, coverage_regressions = _coverage_summary(publishable_rows, baseline)
    global_floor = int(baseline.get("min_draft_publishable") or 0)
    if global_floor and len(publishable_rows) < global_floor:
        coverage_regressions.append(
            {
                "code": "PUBLISHABLE_COVERAGE_REGRESSION",
                "actual": len(publishable_rows),
                "floor": global_floor,
            }
        )

    engineering_pass = (
        not engineering_gates and not unhandled_errors and not coverage_regressions
    )
    if engineering_pass and proof_gates:
        acceptance = "ENGINEERING_PASS_EXTERNAL_PROOF_PENDING"
    elif engineering_pass:
        acceptance = "ENGINEERING_PASS"
    else:
        acceptance = "ENGINEERING_FAILURES_PRESENT"

    return {
        "run_id": manifest.get("run_id"),
        "git_commit_sha": manifest.get("git_commit_sha"),
        "issuer_count": manifest.get("issuer_count"),
        "downloaded_filing_count": manifest.get("downloaded_filing_count"),
        "extracted_filing_count": manifest.get("extracted_filing_count"),
        "pipeline_error_count": expected_error_count,
        "quarantined_pipeline_error_count": len(quarantined_errors),
        "quarantined_pipeline_errors": quarantined_errors,
        "unhandled_pipeline_error_count": len(unhandled_errors),
        "unhandled_pipeline_errors": unhandled_errors,
        "max_quarantined_extraction_timeouts": max(
            0, int(baseline.get("max_quarantined_extraction_timeouts") or 0)
        ),
        "fact_status_counts": manifest.get("fact_status_counts"),
        "draft_publishable_count": len(publishable_rows),
        "coverage": coverage,
        "coverage_regression_count": len(coverage_regressions),
        "coverage_regressions": coverage_regressions,
        "retry_summary": manifest.get("retry_summary"),
        "engineering_gate_count": len(engineering_gates),
        "engineering_gates": engineering_gates,
        "external_proof_gates": proof_gates,
        "review_failure_families": dict(review_counts.most_common()),
        "acceptance": acceptance,
    }
