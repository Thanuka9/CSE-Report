"""EPS consistency validation — applicability-gated, never invents EPS."""

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

EPS_RECONCILIATION = ValidationRule(
    rule_id="EPS_RECONCILIATION",
    inputs=("PAT", "EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED"),
    applicability="WHEN_PAT_AND_EPS_AND_IMPLIED_SHARES",
    severity="RETRY",
    tolerance_relative=0.05,
    description="When PAT and EPS exist, implied share count should be plausible.",
)


def evaluate_eps_reconciliation(
    facts: Mapping[str, ExtractedFact],
    rule: ValidationRule = EPS_RECONCILIATION,
) -> ValidationResult:
    pat = published_value(facts.get("PAT"))
    eps = (
        published_value(facts.get("EPS_SELECTED"))
        or published_value(facts.get("EPS_DILUTED"))
        or published_value(facts.get("EPS_BASIC"))
    )
    if pat is None or eps is None or eps == 0:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.NOT_APPLICABLE,
            "Need published PAT and EPS",
        )
    implied_shares = abs(pat / eps)
    # CSE quarterly EPS is usually for millions of shares; reject absurd scales.
    if implied_shares < Decimal("1000") or implied_shares > Decimal("1e12"):
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.FAIL,
            f"Implied shares {implied_shares} outside plausible band",
            evidence={"pat": str(pat), "eps": str(eps), "implied_shares": str(implied_shares)},
        )
    # Soft check: recomputed EPS from implied shares should match closely by construction;
    # use relative band around published EPS for rounding.
    recomputed = pat / implied_shares
    difference, tolerance, ok = relative_difference(
        abs(eps), abs(recomputed), relative=rule.tolerance_relative, floor=Decimal("0.0001")
    )
    if ok:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.PASS,
            "EPS and PAT imply a plausible share count",
            difference=difference,
            tolerance=tolerance,
            evidence={"pat": str(pat), "eps": str(eps), "implied_shares": str(implied_shares)},
        )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.WARN,
        "EPS/PAT relationship outside tolerance",
        difference=difference,
        tolerance=tolerance,
        evidence={"pat": str(pat), "eps": str(eps), "implied_shares": str(implied_shares)},
    )
