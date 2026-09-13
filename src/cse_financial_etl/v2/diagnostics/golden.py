"""Golden-corpus scoring. Aggregate coverage alone is not acceptance."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import EntityScope, PublicationStatus, ValidationStatus
from cse_financial_etl.v2.contracts.facts import SourceFact


class GoldenFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    metric_code: str
    raw_value: Decimal
    normalized_value: Decimal
    entity_scope: EntityScope
    period_end: date
    duration_months: int | None
    unit_scale: Decimal | None = None
    page: int
    reviewer: str
    review_date: date


class GoldenReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    expected_count: int
    predicted_count: int
    true_positives: int
    precision: float
    source_reported_recall: float
    entity_accuracy: float
    period_accuracy: float
    duration_accuracy: float
    unit_accuracy: float
    numeric_accuracy: float
    critical_wrong_populated: int


class GoldenGates(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    passed: bool
    failures: tuple[str, ...]


def _match_key(metric: str, entity: EntityScope, period: date) -> tuple[str, EntityScope, date]:
    return (metric, entity, period)


def published_source_facts(facts: tuple[SourceFact, ...]) -> tuple[SourceFact, ...]:
    """Publication-facing golden scoring ignores withheld/failed facts."""

    return tuple(
        fact
        for fact in facts
        if fact.publication_status is not PublicationStatus.WITHHELD
        and fact.validation_status is not ValidationStatus.FAILED
    )


def score_golden(
    expected: tuple[GoldenFact, ...],
    predicted: tuple[SourceFact, ...],
    *,
    published_only: bool = True,
) -> GoldenReport:
    if published_only:
        predicted = published_source_facts(predicted)
    exp_map = {
        _match_key(item.metric_code, item.entity_scope, item.period_end): item for item in expected
    }
    pred_groups: dict[tuple[str, EntityScope, date], list[SourceFact]] = {}
    for item in predicted:
        pred_groups.setdefault(
            _match_key(item.metric_code, item.entity_scope, item.period_end), []
        ).append(item)
    shared = set(exp_map) & set(pred_groups)
    tp = 0
    wrong = 0
    entity_ok = period_ok = duration_ok = unit_ok = numeric_ok = 0
    unit_scored = 0
    for key in shared:
        gold = exp_map[key]
        preds = pred_groups[key]
        matched = next(
            (item for item in preds if item.normalized_value == gold.normalized_value), None
        )
        if matched is None:
            wrong += 1
            continue
        tp += 1
        entity_ok += int(matched.entity_scope is gold.entity_scope)
        period_ok += int(matched.period_end == gold.period_end)
        duration_ok += int(matched.duration_months == gold.duration_months)
        if gold.unit_scale is not None:
            unit_scored += 1
            unit_ok += int((matched.source_scale or Decimal("1")) == gold.unit_scale)
        numeric_ok += 1
    false_pos = max(len(pred_groups) - tp, 0)
    precision = tp / max(tp + false_pos, 1)
    recall = tp / max(len(exp_map), 1)
    denom = max(tp, 1)
    return GoldenReport(
        expected_count=len(expected),
        predicted_count=len(predicted),
        true_positives=tp,
        precision=precision,
        source_reported_recall=recall,
        entity_accuracy=entity_ok / denom,
        period_accuracy=period_ok / denom,
        duration_accuracy=duration_ok / denom,
        unit_accuracy=(unit_ok / unit_scored) if unit_scored else 1.0,
        numeric_accuracy=numeric_ok / denom,
        critical_wrong_populated=wrong,
    )


GOLDEN_TARGETS: dict[str, float] = {
    "critical_wrong_populated": 0,
    "entity_accuracy": 0.998,
    "period_accuracy": 0.998,
    "duration_accuracy": 0.998,
    "unit_accuracy": 0.998,
    "numeric_accuracy": 0.995,
    "source_reported_recall": 0.97,
}


def aggregate_golden_reports(reports: tuple[GoldenReport, ...]) -> GoldenReport:
    expected = sum(item.expected_count for item in reports)
    predicted = sum(item.predicted_count for item in reports)
    tp = sum(item.true_positives for item in reports)
    wrong = sum(item.critical_wrong_populated for item in reports)

    def weighted(attr: str) -> float:
        numerator = 0.0
        denominator = 0
        for report in reports:
            if report.true_positives == 0:
                continue
            numerator += float(getattr(report, attr)) * report.true_positives
            denominator += report.true_positives
        return numerator / max(denominator, 1)

    return GoldenReport(
        expected_count=expected,
        predicted_count=predicted,
        true_positives=tp,
        precision=tp / max(predicted, 1),
        source_reported_recall=tp / max(expected, 1),
        entity_accuracy=weighted("entity_accuracy"),
        period_accuracy=weighted("period_accuracy"),
        duration_accuracy=weighted("duration_accuracy"),
        unit_accuracy=weighted("unit_accuracy"),
        numeric_accuracy=weighted("numeric_accuracy"),
        critical_wrong_populated=wrong,
    )


def evaluate_golden_gates(report: GoldenReport) -> GoldenGates:
    failures: list[str] = []
    if report.critical_wrong_populated != int(GOLDEN_TARGETS["critical_wrong_populated"]):
        failures.append(f"critical_wrong_populated={report.critical_wrong_populated}")
    checks = (
        ("entity_accuracy", report.entity_accuracy),
        ("period_accuracy", report.period_accuracy),
        ("duration_accuracy", report.duration_accuracy),
        ("unit_accuracy", report.unit_accuracy),
        ("numeric_accuracy", report.numeric_accuracy),
        ("source_reported_recall", report.source_reported_recall),
    )
    for name, value in checks:
        floor = GOLDEN_TARGETS[name]
        if value < floor:
            failures.append(f"{name}={value:.6f} < {floor}")
    return GoldenGates(passed=not failures, failures=tuple(failures))
