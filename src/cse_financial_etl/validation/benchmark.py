from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact

CONTEXT_FIELDS = (
    "metric_code",
    "entity_scope",
    "period_end",
    "source_year",
    "duration_months",
    "comparison_role",
    "unit",
    "raw_value",
    "normalized_value",
    "source_page",
    "source_evidence",
    "validation_status",
)


@dataclass(frozen=True, slots=True)
class ExpectedFact:
    metric_code: str
    entity_scope: str
    period_end: date
    source_year: int
    duration_months: int | None
    comparison_role: str
    raw_value: str
    normalized_value: str
    validation_status: str = "PASSED"
    status: str = "EXTRACTED"
    source_page: int | None = None
    unit_scale: int | None = None
    unit_currency: str | None = None
    rejected_raw_values: tuple[str, ...] = ()


@dataclass(slots=True)
class FieldResult:
    field: str
    passed: bool
    expected: str
    actual: str


@dataclass(slots=True)
class CaseResult:
    case_id: str
    family: str
    passed: bool
    failure_class: str
    fields: list[FieldResult] = field(default_factory=list)
    detail: str = ""

    @property
    def wrong_populated(self) -> bool:
        return self.failure_class == "WRONG_POPULATED_VALUE"

    @property
    def false_missing(self) -> bool:
        return self.failure_class == "FALSE_MISSING"


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def evidence_dict(fact: ExtractedFact | None) -> dict[str, Any]:
    if fact is None or not fact.evidence_json:
        return {}
    try:
        payload = json.loads(fact.evidence_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def discovered_raw_values(fact: ExtractedFact | None) -> set[str]:
    evidence = evidence_dict(fact)
    found: set[str] = set()
    for item in evidence.get("column_raw_values", []):
        found.add(str(item).replace(",", ""))
    for item in evidence.get("rejected_raw_values", []):
        found.add(str(item).replace(",", ""))
    for row in evidence.get("candidate_scores", []):
        found.add(str(row.get("raw_value", "")).replace(",", ""))
    for row in evidence.get("graph", {}).get("column_scores", []):
        found.add(str(row.get("raw", "")).replace(",", ""))
    if fact is not None and fact.raw_text:
        found.add(fact.raw_text.replace(",", ""))
    return {item for item in found if item}


def classify_failure(expected: ExpectedFact, fact: ExtractedFact | None) -> str:
    if fact is None or fact.status not in {"EXTRACTED", "EXTRACTED_DERIVED", "LOW_CERTAINTY"}:
        return "FALSE_MISSING"
    actual = fact.normalized_value
    wanted = _dec(expected.normalized_value)
    if actual is None:
        return "FALSE_MISSING"
    if wanted is not None and actual != wanted:
        return "WRONG_POPULATED_VALUE"
    return "CONTEXT_MISMATCH"


def check_extracted_fact(
    *,
    case_id: str,
    family: str,
    fact: ExtractedFact | None,
    expected: ExpectedFact,
    discovered: set[str] | None = None,
) -> CaseResult:
    """Assert the published number and the context that made it legal."""

    fields: list[FieldResult] = []
    evidence = evidence_dict(fact)
    source_year = evidence.get("source_header_year")
    if source_year is None and fact is not None and fact.comparison_role == "CURRENT":
        source_year = fact.period_end.year
    unit_scale = fact.scale_factor if fact else None
    unit_currency = fact.currency if fact else None
    checks = {
        "metric_code": (expected.metric_code, fact.metric_code if fact else None),
        "entity_scope": (expected.entity_scope, fact.entity_scope if fact else None),
        "period_end": (
            expected.period_end.isoformat(),
            fact.period_end.isoformat() if fact else None,
        ),
        "source_year": (str(expected.source_year), str(source_year) if source_year else None),
        "duration_months": (
            "" if expected.duration_months is None else str(expected.duration_months),
            (
                ""
                if fact is None or fact.duration_months is None
                else str(fact.duration_months)
            ),
        ),
        "comparison_role": (
            expected.comparison_role,
            fact.comparison_role if fact else None,
        ),
        "unit": (
            f"{expected.unit_currency or 'LKR'}:{expected.unit_scale}",
            f"{unit_currency}:{unit_scale}" if fact else None,
        ),
        "raw_value": (
            expected.raw_value.replace(",", ""),
            (fact.raw_text or str(fact.raw_value or "")).replace(",", "") if fact else None,
        ),
        "normalized_value": (
            str(_dec(expected.normalized_value)),
            str(fact.normalized_value) if fact and fact.normalized_value is not None else None,
        ),
        "source_page": (
            str(expected.source_page) if expected.source_page is not None else "*",
            str(fact.source_page) if fact and fact.source_page is not None else None,
        ),
        "source_evidence": (
            "present",
            "present" if fact and (fact.source_line or fact.evidence_json) else None,
        ),
        "validation_status": (
            expected.validation_status,
            fact.validation_status if fact else None,
        ),
    }
    if expected.unit_scale is None:
        checks.pop("unit")
    if expected.source_page is None:
        checks["source_page"] = ("*", "*")

    for name, (wanted, actual) in checks.items():
        passed = wanted in {"*", None} or str(wanted) == str(actual)
        if name == "raw_value" and wanted and actual:
            passed = _dec(wanted) == _dec(actual)
        if name == "normalized_value" and wanted and actual:
            passed = _dec(wanted) == _dec(actual)
        fields.append(FieldResult(name, passed, str(wanted), str(actual)))

    seen = discovered if discovered is not None else discovered_raw_values(fact)
    rejected_ok = True
    missing_rejected: list[str] = []
    for raw in expected.rejected_raw_values:
        token = raw.replace(",", "")
        if token not in seen and _dec(token) not in {_dec(item) for item in seen}:
            rejected_ok = False
            missing_rejected.append(raw)
    fields.append(
        FieldResult(
            "rejected_candidates",
            rejected_ok,
            ",".join(expected.rejected_raw_values) or "none",
            "seen" if rejected_ok else f"missing:{','.join(missing_rejected)}",
        )
    )

    passed = all(item.passed for item in fields)
    if passed:
        failure_class = "PASS"
    else:
        failure_class = classify_failure(expected, fact)
        if failure_class == "WRONG_POPULATED_VALUE":
            pass
        elif fact is not None and fact.status in {"EXTRACTED", "EXTRACTED_DERIVED"}:
            if any(item.field == "normalized_value" and not item.passed for item in fields):
                failure_class = "WRONG_POPULATED_VALUE"
            elif not rejected_ok:
                failure_class = "REJECTED_CANDIDATE_NOT_PROVEN"
            else:
                failure_class = "CONTEXT_MISMATCH"
    return CaseResult(case_id, family, passed, failure_class, fields)


def dashboard(results: list[CaseResult]) -> dict[str, Any]:
    """Accuracy-hardening metrics. Wrong populated values outrank blanks."""

    total = len(results) or 1
    counts = Counter(result.failure_class for result in results)
    field_fail = Counter(
        field.field for result in results for field in result.fields if not field.passed
    )
    families = sorted({result.family for result in results})
    by_family = []
    for family in families:
        subset = [result for result in results if result.family == family]
        by_family.append(
            {
                "family": family,
                "cases": len(subset),
                "passed": sum(result.passed for result in subset),
                "wrong_populated": sum(result.wrong_populated for result in subset),
                "false_missing": sum(result.false_missing for result in subset),
            }
        )
    return {
        "phase": "Architecture complete; validation and accuracy-hardening underway",
        "case_count": len(results),
        "passed": sum(result.passed for result in results),
        "metrics": {
            "exact_numeric_accuracy": 1 - (field_fail["normalized_value"] / total),
            "current_comparative_accuracy": 1 - (field_fail["comparison_role"] / total),
            "three_month_ytd_accuracy": 1 - (field_fail["duration_months"] / total),
            "company_group_accuracy": 1 - (field_fail["entity_scope"] / total),
            "unit_accuracy": 1 - (field_fail["unit"] / total),
            "false_missing_rate": sum(result.false_missing for result in results) / total,
            "wrong_populated_value_rate": (
                sum(result.wrong_populated for result in results) / total
            ),
            "review_rate": counts.get("FALSE_MISSING", 0) / total,
            "rejected_candidate_proof_rate": 1 - (field_fail["rejected_candidates"] / total),
        },
        "failure_classes": dict(counts),
        "by_family": by_family,
        "failures": [
            {
                "case_id": result.case_id,
                "family": result.family,
                "failure_class": result.failure_class,
                "fields": [
                    {
                        "field": field.field,
                        "expected": field.expected,
                        "actual": field.actual,
                    }
                    for field in result.fields
                    if not field.passed
                ],
            }
            for result in results
            if not result.passed
        ],
    }


def write_dashboard(project_root: Path, payload: dict[str, Any]) -> Path:
    destination = project_root / "outputs" / "benchmarks" / "structure_accuracy.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(destination)
    return destination
