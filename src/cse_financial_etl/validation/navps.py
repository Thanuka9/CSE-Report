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
    inputs=("TOTAL_EQUITY", "NAVPS", "WEIGHTED_AVG_SHARES"),
    applicability="WHEN_EQUITY_AND_NAVPS_AND_INDEPENDENT_SHARES",
    severity="RETRY",
    tolerance_relative=0.05,
    description=(
        "When Equity, NAVPS and an independently sourced share count exist, "
        "recompute NAVPS from equity / shares."
    ),
)

_SHARE_METRIC_CODES = ("WEIGHTED_AVG_SHARES", "ORDINARY_SHARES", "SHARE_COUNT")


def _independent_shares(facts: Mapping[str, ExtractedFact]) -> Decimal | None:
    for code in _SHARE_METRIC_CODES:
        shares = published_value(facts.get(code))
        if shares is not None and shares != 0:
            return abs(shares)
    return None


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

    shares = _independent_shares(facts)
    if shares is None:
        implied = abs(equity / navps)
        if implied < Decimal("1000") or implied > Decimal("1e12"):
            return ValidationResult(
                rule.rule_id,
                ValidationOutcome.FAIL,
                f"Implied shares from NAVPS {implied} outside plausible band "
                "(no independent denominator)",
                evidence={
                    "equity": str(equity),
                    "navps": str(navps),
                    "implied_shares": str(implied),
                },
            )
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.UNTESTED,
            "Independent NAVPS reconciliation untested: no extracted share-count denominator",
            evidence={
                "equity": str(equity),
                "navps": str(navps),
                "implied_shares": str(implied),
                "independent_shares": None,
            },
        )

    recomputed = equity / shares
    difference, tolerance, ok = relative_difference(
        abs(navps), abs(recomputed), relative=rule.tolerance_relative, floor=Decimal("0.0001")
    )
    evidence = {
        "equity": str(equity),
        "navps": str(navps),
        "independent_shares": str(shares),
        "recomputed_navps": str(recomputed),
    }
    outcome = ValidationOutcome.PASS if ok else ValidationOutcome.FAIL
    return ValidationResult(
        rule.rule_id,
        outcome,
        "NAVPS reconciles to Equity / independently sourced shares"
        if ok
        else "NAVPS does not reconcile to Equity / independently sourced shares",
        difference=difference,
        tolerance=tolerance,
        evidence=evidence,
    )
