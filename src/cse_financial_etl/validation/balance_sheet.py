"""Balance-sheet identity validation — Assets ≈ Liabilities + Equity."""

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

BALANCE_SHEET_IDENTITY = ValidationRule(
    rule_id="BALANCE_SHEET_IDENTITY",
    inputs=("TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_EQUITY"),
    applicability="ALL",
    severity="BLOCKING",
    tolerance_relative=0.005,
    description="Validate explicit Assets ≈ Liabilities + Equity. Never invent liabilities.",
)

BALANCE_SHEET_SANITY = ValidationRule(
    rule_id="BALANCE_SHEET_SANITY",
    inputs=("TOTAL_ASSETS", "TOTAL_EQUITY"),
    applicability="WHEN_BOTH_PRESENT",
    severity="BLOCKING",
    tolerance_relative=0.0,
    description="Assets must not be less than Equity for the same standalone entity.",
)


def evaluate_balance_sheet_identity(
    facts: Mapping[str, ExtractedFact],
    rule: ValidationRule = BALANCE_SHEET_IDENTITY,
) -> ValidationResult:
    assets = published_value(facts.get("TOTAL_ASSETS"))
    liabilities = published_value(facts.get("TOTAL_LIABILITIES"))
    equity = published_value(facts.get("TOTAL_EQUITY"))
    if assets is None or liabilities is None or equity is None:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.INSUFFICIENT_EVIDENCE,
            "Need published Assets, Liabilities, and Equity",
        )
    rhs = liabilities + equity
    difference, tolerance, ok = relative_difference(
        assets, rhs, relative=rule.tolerance_relative
    )
    if ok:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.PASS,
            "Assets reconcile to Liabilities + Equity",
            difference=difference,
            tolerance=tolerance,
            evidence={
                "assets": str(assets),
                "liabilities": str(liabilities),
                "equity": str(equity),
            },
        )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.FAIL,
        f"Assets - liabilities - equity = {difference}; tolerance = {tolerance}",
        difference=difference,
        tolerance=tolerance,
        evidence={
            "assets": str(assets),
            "liabilities": str(liabilities),
            "equity": str(equity),
        },
    )


def evaluate_balance_sheet_sanity(
    facts: Mapping[str, ExtractedFact],
    rule: ValidationRule = BALANCE_SHEET_SANITY,
) -> ValidationResult:
    assets = published_value(facts.get("TOTAL_ASSETS"))
    equity = published_value(facts.get("TOTAL_EQUITY"))
    if assets is None or equity is None:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.INSUFFICIENT_EVIDENCE,
            "Need published Assets and Equity",
        )
    if assets < equity:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.FAIL,
            "Total assets are less than total equity",
            difference=equity - assets,
            tolerance=Decimal(0),
            evidence={"assets": str(assets), "equity": str(equity)},
        )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.PASS,
        "Assets >= Equity",
        evidence={"assets": str(assets), "equity": str(equity)},
    )
