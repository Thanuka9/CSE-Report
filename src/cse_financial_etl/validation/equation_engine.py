"""Deterministic financial validation-rule registry (Phase One).

Equations validate independently extracted facts. They never invent substitute values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact


class ValidationOutcome(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class ValidationRule:
    rule_id: str
    inputs: tuple[str, ...]
    applicability: str
    severity: str
    tolerance_relative: float = 0.005
    description: str = ""


@dataclass(frozen=True, slots=True)
class ValidationResult:
    rule_id: str
    outcome: ValidationOutcome
    detail: str = ""
    difference: Decimal | None = None
    tolerance: Decimal | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "outcome": self.outcome.value,
            "detail": self.detail,
            "difference": str(self.difference) if self.difference is not None else None,
            "tolerance": str(self.tolerance) if self.tolerance is not None else None,
            "evidence": self.evidence,
        }


RuleEvaluator = Callable[
    [Mapping[str, ExtractedFact], ValidationRule],
    ValidationResult,
]


class EquationEngine:
    """Registry of equation rules evaluated against an issuer/period fact map."""

    def __init__(self) -> None:
        self._rules: list[tuple[ValidationRule, RuleEvaluator]] = []

    def register(self, rule: ValidationRule, evaluator: RuleEvaluator) -> None:
        self._rules.append((rule, evaluator))

    @property
    def rules(self) -> list[ValidationRule]:
        return [rule for rule, _ in self._rules]

    def evaluate(self, facts: Mapping[str, ExtractedFact]) -> list[ValidationResult]:
        return [evaluator(facts, rule) for rule, evaluator in self._rules]

    def blocking_failures(self, facts: Mapping[str, ExtractedFact]) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for rule, evaluator in self._rules:
            result = evaluator(facts, rule)
            if result.outcome == ValidationOutcome.FAIL and rule.severity == "BLOCKING":
                results.append(result)
        return results


def published_value(fact: ExtractedFact | None) -> Decimal | None:
    if fact is None:
        return None
    if fact.status not in {"EXTRACTED", "EXTRACTED_DERIVED", "LOW_CERTAINTY"}:
        return None
    return fact.normalized_value


def relative_difference(
    left: Decimal,
    right: Decimal,
    *,
    relative: float,
    floor: Decimal = Decimal(1),
) -> tuple[Decimal, Decimal, bool]:
    difference = abs(left - right)
    basis = abs(left) if left != 0 else abs(right)
    tolerance = max(basis * Decimal(str(relative)), floor)
    return difference, tolerance, difference <= tolerance
