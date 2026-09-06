"""Market capitalization reconciliation for current snapshot fields."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from cse_financial_etl.validation.equation_engine import (
    ValidationOutcome,
    ValidationResult,
    ValidationRule,
    relative_difference,
)

MARKET_CAP_RECONCILIATION = ValidationRule(
    rule_id="MARKET_CAP_RECONCILIATION",
    inputs=("CURRENT_PRICE", "ISSUED_QUANTITY", "MARKET_CAPITALIZATION"),
    applicability="WHEN_ALL_THREE_PRESENT",
    severity="WARN",
    tolerance_relative=0.01,
    description="Market Cap ≈ Current Price × Issued Quantity",
)


def evaluate_market_cap_reconciliation(
    security: Mapping[str, Any],
    rule: ValidationRule = MARKET_CAP_RECONCILIATION,
) -> ValidationResult:
    try:
        price = Decimal(str(security["price"])) if security.get("price") is not None else None
        issued = (
            Decimal(str(security["issued_quantity"]))
            if security.get("issued_quantity") is not None
            else None
        )
        market_cap = (
            Decimal(str(security["market_capitalization"]))
            if security.get("market_capitalization") is not None
            else None
        )
    except Exception:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.INSUFFICIENT_EVIDENCE,
            "Unparseable market snapshot fields",
        )
    if price is None or issued is None or market_cap is None:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.NOT_APPLICABLE,
            "Need price, issued quantity, and market capitalization",
        )
    expected = price * issued
    difference, tolerance, ok = relative_difference(
        market_cap, expected, relative=rule.tolerance_relative, floor=Decimal("1")
    )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.PASS if ok else ValidationOutcome.FAIL,
        "Market cap reconciles to price × issued quantity"
        if ok
        else f"Market cap mismatch difference={difference}",
        difference=difference,
        tolerance=tolerance,
        evidence={
            "price": str(price),
            "issued_quantity": str(issued),
            "market_capitalization": str(market_cap),
            "expected": str(expected),
        },
    )
