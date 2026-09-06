"""Cross-metric header/context consistency for one-quarter P&L facts."""

from __future__ import annotations

from collections.abc import Mapping

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.equation_engine import (
    ValidationOutcome,
    ValidationResult,
    ValidationRule,
)

CROSS_METRIC_CONTEXT = ValidationRule(
    rule_id="CROSS_METRIC_CONTEXT_INCONSISTENT",
    inputs=("TOP_LINE", "OPERATING_PROFIT", "PBT", "PAT", "EPS_BASIC", "EPS_DILUTED"),
    applicability="WHEN_TWO_OR_MORE_FLOW_EXTRACTED",
    severity="RETRY",
    description="Flow metrics must share entity, duration, and comparison role.",
)

FLOW_CONTEXT_CODES = frozenset(CROSS_METRIC_CONTEXT.inputs)


def evaluate_cross_metric_context(
    facts: Mapping[str, ExtractedFact],
    rule: ValidationRule = CROSS_METRIC_CONTEXT,
) -> ValidationResult:
    extracted = [
        fact
        for code in rule.inputs
        if (fact := facts.get(code)) is not None
        and fact.status in {"EXTRACTED", "LOW_CERTAINTY"}
    ]
    if len(extracted) < 2:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.NOT_APPLICABLE,
            "Fewer than two published flow metrics",
        )
    scopes = {fact.entity_scope for fact in extracted}
    durations = {fact.duration_months for fact in extracted}
    roles = {fact.comparison_role for fact in extracted}
    if len(scopes) > 1 or len(durations) > 1 or len(roles) > 1:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.FAIL,
            (
                "Flow metrics resolved through inconsistent entity, duration, or comparison paths: "
                f"scopes={sorted(scopes)} durations={sorted(str(item) for item in durations)} "
                f"roles={sorted(roles)}"
            ),
            evidence={
                "scopes": sorted(scopes),
                "durations": [str(item) for item in sorted(durations, key=lambda x: (x is None, x))],
                "roles": sorted(roles),
                "metrics": [fact.metric_code for fact in extracted],
            },
        )
    confidences = [fact.entity_confidence for fact in extracted]
    pages = {fact.source_page for fact in extracted}
    if len(pages) > 1 and max(confidences) - min(confidences) >= 0.3:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.WARN,
            "Flow metrics resolved through inconsistent header/period paths",
            evidence={
                "pages": sorted(str(page) for page in pages),
                "entity_confidence_span": round(max(confidences) - min(confidences), 4),
            },
        )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.PASS,
        "Flow metrics share entity/duration/comparison context",
        evidence={"metrics": [fact.metric_code for fact in extracted]},
    )
