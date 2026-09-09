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
    inputs=("PAT", "EPS_BASIC", "EPS_DILUTED", "EPS_SELECTED", "WEIGHTED_AVG_SHARES"),
    applicability="WHEN_PAT_AND_EPS_AND_INDEPENDENT_SHARES",
    severity="RETRY",
    tolerance_relative=0.05,
    description=(
        "When PAT, EPS and an independently sourced share count exist, "
        "recompute EPS from attributable earnings / shares."
    ),
)

_SHARE_METRIC_CODES = ("WEIGHTED_AVG_SHARES", "ORDINARY_SHARES", "SHARE_COUNT")


def _independent_shares(facts: Mapping[str, ExtractedFact]) -> Decimal | None:
    for code in _SHARE_METRIC_CODES:
        shares = published_value(facts.get(code))
        if shares is not None and shares != 0:
            return shares
    return None


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
    if pat is None or eps is None:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.NOT_APPLICABLE,
            "Need published PAT and EPS",
        )

    shares = _independent_shares(facts)
    if shares is None:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.UNTESTED,
            "Independent EPS reconciliation untested: no extracted share-count denominator",
            evidence={"pat": str(pat), "eps": str(eps), "independent_shares": None},
        )

    recomputed = pat / shares
    difference, tolerance, ok = relative_difference(
        eps, recomputed, relative=rule.tolerance_relative, floor=Decimal("0.0001")
    )
    evidence = {
        "pat": str(pat),
        "eps": str(eps),
        "independent_shares": str(shares),
        "recomputed_eps": str(recomputed),
    }
    if ok:
        return ValidationResult(
            rule.rule_id,
            ValidationOutcome.PASS,
            "EPS reconciles to PAT / independently sourced shares",
            difference=difference,
            tolerance=tolerance,
            evidence=evidence,
        )
    return ValidationResult(
        rule.rule_id,
        ValidationOutcome.FAIL,
        "EPS does not reconcile to PAT / independently sourced shares",
        difference=difference,
        tolerance=tolerance,
        evidence=evidence,
    )
