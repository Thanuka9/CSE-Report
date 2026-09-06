"""NAVPS consistency validation — applicability-gated."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.equation_engine import (
    ValidationOutcome,
    ValidationResult,
    ValidationRule,
    published_value,
    relative_difference,
)

NAVPS_RECONCILIATION = ValidationRule(
    rule_id="NAVPS_RECONCILIATION",
    inputs=("TOTAL_EQUITY", "NAVPS"),
    applicability="WHEN_EQUITY_AND_NAVPS",
    severity="RETRY",
    tolerance_relative=0.05,
    description="When Equity and NAVPS exist, implied shares should be plausible.",
)


def evaluate_navps_reconciliation(
    facts: Mapping[str, ExtractedFact],
    rule: ValidationRule = NAVPS_RECONCILIATION,
) -> ValidationResult:
    equity = published_value(facts.get("TOTAL_EQUITY"))
    navps = published_value(facts.get("NAVPS"))
    if equity is None or navps is None or navps == 0:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.NOT_APPLICABLE,
            "Need published Equity and NAVPS",
        )
    implied_shares = abs(equity / navps)
    if implied_shares < Decimal("1000") or implied_shares > Decimal("1e12"):
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.FAIL,
            f"Implied shares from NAVPS {implied_shares} outside plausible band",
            evidence={
                "equity": str(equity),
                "navps": str(navps),
                "implied_shares": str(implied_shares),
            },
        )
    recomputed = equity / implied_shares
    difference, tolerance, ok = relative_difference(
        abs(navps), abs(recomputed), relative=rule.tolerance_relative, floor=Decimal("0.0001")
    )
    outcome = ValidationOutcome.PASS if ok else ValidationOutcome.WARN
    return ValidationResult(
        rule.rule_id,
        outcome,
        "NAVPS and Equity imply a plausible share count"
        if ok
        else "NAVPS/Equity relationship outside tolerance",
        difference=difference,
        tolerance=tolerance,
        evidence={
            "equity": str(equity),
            "navps": str(navps),
            "implied_shares": str(implied_shares),
        },
    )
