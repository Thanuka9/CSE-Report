"""Conditional PAT ≈ PBT - tax bridge. Never generates PAT from the equation."""

from __future__ import annotations

import json
import re
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

PAT_TAX_BRIDGE = ValidationRule(
    rule_id="PAT_TAX_BRIDGE",
    inputs=("PBT", "INCOME_TAX", "PAT"),
    applicability="WHEN_TAX_LINE_IDENTIFIED",
    severity="RETRY",
    tolerance_relative=0.02,
    description="When an income-tax line is present, PAT should reconcile to PBT ± tax.",
)

_TAX_LABEL = re.compile(
    r"\b(?:income\s+tax(?:\s+expense)?|taxation|tax\s+expense|tax\s+on\s+profit)\b",
    re.I,
)


def _tax_from_evidence(facts: Mapping[str, ExtractedFact]) -> Decimal | None:
    """Recover tax amount only when a published PBT/PAT pair carries explicit tax evidence."""

    for code in ("PBT", "PAT"):
        fact = facts.get(code)
        if fact is None or not fact.evidence_json:
            continue
        try:
            evidence = json.loads(fact.evidence_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(evidence, dict):
            continue
        tax = evidence.get("income_tax") or evidence.get("tax_expense")
        if tax is None:
            continue
        try:
            return Decimal(str(tax))
        except Exception:
            continue
    return None


def tax_line_identified(facts: Mapping[str, ExtractedFact]) -> bool:
    if facts.get("INCOME_TAX") is not None and published_value(facts.get("INCOME_TAX")) is not None:
        return True
    if _tax_from_evidence(facts) is not None:
        return True
    for code in ("PBT", "PAT"):
        fact = facts.get(code)
        if fact and fact.source_line and _TAX_LABEL.search(fact.source_line):
            return True
    return False


def evaluate_pat_tax_bridge(
    facts: Mapping[str, ExtractedFact],
    rule: ValidationRule = PAT_TAX_BRIDGE,
) -> ValidationResult:
    pbt = published_value(facts.get("PBT"))
    pat = published_value(facts.get("PAT"))
    tax = published_value(facts.get("INCOME_TAX"))
    if tax is None:
        tax = _tax_from_evidence(facts)
    if pbt is None or pat is None:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.INSUFFICIENT_EVIDENCE,
            "Need published PBT and PAT",
        )
    if tax is None or not tax_line_identified(facts):
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.NOT_APPLICABLE,
            "No proven income-tax line for this statement",
        )
    # Accept either PBT - tax or PBT + tax (tax printed as negative expense).
    candidates = (pbt - abs(tax), pbt + tax if tax < 0 else pbt - tax)
    best = min(candidates, key=lambda value: abs(value - pat))
    difference, tolerance, ok = relative_difference(
        pat, best, relative=rule.tolerance_relative, floor=Decimal("0.01")
    )
    evidence = {
        "pbt": str(pbt),
        "pat": str(pat),
        "tax": str(tax),
        "implied_pat": str(best),
    }
    if ok:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.PASS,
            "PAT reconciles to PBT and tax",
            difference=difference,
            tolerance=tolerance,
            evidence=evidence,
        )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.FAIL,
        f"PAT bridge mismatch difference={difference} tolerance={tolerance}",
        difference=difference,
        tolerance=tolerance,
        evidence=evidence,
    )
