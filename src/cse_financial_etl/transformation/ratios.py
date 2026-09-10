from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.acceptance import is_publishable_fact
from cse_financial_etl.validation.row_safety import (
    is_narrative_unit_amount,
    ratio_plausibility_issue,
    suspicious_selected_numeric,
)

ACCEPTED = {"EXTRACTED", "EXTRACTED_DERIVED"}
STANDALONE = {"COMPANY", "BANK"}


def _evidence(fact: ExtractedFact) -> dict[str, Any]:
    if not fact.evidence_json:
        return {}
    try:
        parsed = json.loads(fact.evidence_json)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sanitize_source_fact(fact: ExtractedFact) -> ExtractedFact:
    """Make the final materialized fact set fail closed before derivation.

    ``EXTRACTED`` records are machine extraction candidates, but validation failures,
    unresolved evidence and the explicitly bounded layout fallback must never retain a
    publishable status in the normalized output. Raw source evidence is preserved while
    the normalized value is withheld.
    """

    if fact.status not in ACCEPTED:
        return fact
    evidence = _evidence(fact)
    if is_narrative_unit_amount(fact.unit_source_text):
        evidence["row_safety"] = "NARRATIVE_UNIT_EVIDENCE"
        return replace(
            fact,
            status="UNIT_NOT_RESOLVED",
            normalized_value=None,
            validation_status="FAILED",
            overall_certainty=0.0,
            certainty_band="NONE",
            confidence="LOW",
            evidence_json=json.dumps(evidence, separators=(",", ":")),
        )
    if suspicious_selected_numeric(
        fact.metric_code, fact.raw_value, fact.scale_factor, fact.source_line
    ):
        evidence["row_safety"] = "SUSPICIOUS_OCR_SELECTED_NUMERIC"
        return replace(
            fact,
            status="VALUE_CONTEXT_UNRESOLVED",
            normalized_value=None,
            validation_status="FAILED",
            overall_certainty=0.0,
            certainty_band="NONE",
            confidence="LOW",
            evidence_json=json.dumps(evidence, separators=(",", ":")),
        )
    if fact.validation_status in {"FAILED", "REJECTED"}:
        return replace(
            fact,
            status="VALIDATION_FAILED",
            normalized_value=None,
            overall_certainty=0.0,
            certainty_band="NONE",
            confidence="LOW",
        )
    if evidence.get("explicit_fallback"):
        return replace(
            fact,
            status="EXPLICIT_LAYOUT_FALLBACK_REQUIRED",
            normalized_value=None,
            overall_certainty=0.0,
            certainty_band="NONE",
            confidence="LOW",
        )
    if evidence.get("unresolved"):
        return replace(
            fact,
            status="VALUE_CONTEXT_UNRESOLVED",
            normalized_value=None,
            overall_certainty=0.0,
            certainty_band="NONE",
            confidence="LOW",
        )
    return fact


def _sanitize_eps_selected(facts: list[ExtractedFact]) -> list[ExtractedFact]:
    by_code = {fact.metric_code: fact for fact in facts}
    selected = by_code.get("EPS_SELECTED")
    if selected is None or selected.status not in ACCEPTED:
        return facts

    diluted = by_code.get("EPS_DILUTED")
    basic = by_code.get("EPS_BASIC")
    preferred = None
    if (
        diluted is not None
        and is_publishable_fact(diluted)
        and diluted.validation_status == "PASSED"
    ):
        preferred = diluted
    elif basic is not None and is_publishable_fact(basic) and basic.validation_status == "PASSED":
        preferred = basic

    if (
        preferred is not None
        and selected.normalized_value is not None
        and selected.normalized_value == preferred.normalized_value
        and selected.entity_scope == preferred.entity_scope
        and selected.comparison_role == preferred.comparison_role
    ):
        return facts

    evidence = _evidence(selected)
    evidence["row_safety"] = "EPS_SELECTED_SOURCE_NOT_PUBLISHABLE"
    evidence["preferred_source"] = preferred.metric_code if preferred is not None else None
    replacement = replace(
        selected,
        status="VALIDATION_FAILED",
        normalized_value=None,
        validation_status="FAILED",
        overall_certainty=0.0,
        certainty_band="NONE",
        confidence="LOW",
        evidence_json=json.dumps(evidence, separators=(",", ":")),
    )
    return [replacement if fact.metric_code == "EPS_SELECTED" else fact for fact in facts]


def _index_facts(
    facts_by_filing: Iterable[tuple[object, list[ExtractedFact]]],
) -> dict[tuple[str, date, str], ExtractedFact]:
    return {
        (fact.issuer_name, fact.period_end, fact.metric_code): fact
        for _item, facts in facts_by_filing
        for fact in facts
    }


def _accepted(fact: ExtractedFact | None) -> ExtractedFact | None:
    if fact is None or not is_publishable_fact(fact):
        return None
    return fact


def _missing_ratio(
    template: ExtractedFact,
    metric_code: str,
    status: str,
    detail: str,
) -> ExtractedFact:
    return replace(
        template,
        metric_code=metric_code,
        metric_type="RATIO",
        raw_text=None,
        raw_value=None,
        normalized_value=None,
        currency=None,
        scale_factor=None,
        source_page=None,
        source_line=detail,
        unit_source_text=None,
        confidence="NONE",
        status=status,
        raw_label=metric_code,
        source_bbox=None,
        extraction_method="DETERMINISTIC_DERIVATION",
        semantic_model="rule",
        semantic_confidence=1.0,
        overall_certainty=0.0,
        certainty_band="NONE",
        duration_months=3,
        validation_status="FAILED",
        review_status="REVIEW",
        evidence_json=json.dumps({"reason": status, "detail": detail}, separators=(",", ":")),
    )


def _ratio_fact(
    template: ExtractedFact,
    metric_code: str,
    value: Decimal,
    inputs: dict[str, str],
    formula: str,
    certainty: float,
    *,
    entity_scope: str,
) -> ExtractedFact:
    band = "HIGH" if certainty >= 0.9 else "MEDIUM" if certainty >= 0.75 else "LOW"
    return replace(
        template,
        metric_code=metric_code,
        metric_type="RATIO",
        raw_text=None,
        raw_value=None,
        normalized_value=value,
        currency=None,
        scale_factor=1,
        entity_scope=entity_scope,
        comparison_role="CURRENT",
        source_page=None,
        source_line=formula,
        unit_source_text="DERIVED_RATIO",
        confidence=band,
        status="EXTRACTED_DERIVED",
        raw_label=metric_code,
        source_bbox=None,
        extraction_method="DETERMINISTIC_DERIVATION",
        semantic_model="rule",
        semantic_confidence=1.0,
        entity_confidence=1.0,
        period_confidence=1.0,
        unit_confidence=1.0,
        column_confidence=1.0,
        validation_confidence=0.98,
        overall_certainty=round(certainty, 4),
        certainty_band=band,
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
        evidence_json=json.dumps(
            {
                "formula": formula,
                "inputs": inputs,
                "derived_value": str(value),
                "entity_scope": entity_scope,
                "comparison_role": "CURRENT",
                "period_end": template.period_end.isoformat(),
            },
            separators=(",", ":"),
        ),
    )


def _same_quarter_ratio(
    *,
    index: dict[tuple[str, date, str], ExtractedFact],
    template: ExtractedFact,
    issuer_name: str,
    period_end: date,
    numerator_code: str,
    denominator_code: str,
    ratio_code: str,
    formula: str,
    empty_denominator_reason: str,
) -> ExtractedFact:
    """Compute a ratio from compatible, current facts in the same filing period only."""

    numerator = _accepted(index.get((issuer_name, period_end, numerator_code)))
    denominator = _accepted(index.get((issuer_name, period_end, denominator_code)))
    if numerator is None or denominator is None:
        missing = denominator_code if denominator is None else numerator_code
        return _missing_ratio(
            template,
            ratio_code,
            "INSUFFICIENT_INPUT",
            f"{ratio_code} needs approved same-quarter {missing}.",
        )
    if numerator.currency != denominator.currency:
        return _missing_ratio(
            template,
            ratio_code,
            "INCOMPATIBLE_CURRENCY",
            f"{numerator_code} and {denominator_code} currencies differ.",
        )
    if numerator.entity_scope != denominator.entity_scope:
        return _missing_ratio(
            template,
            ratio_code,
            "INCOMPATIBLE_SCOPE",
            f"{numerator_code} and {denominator_code} entity scopes differ.",
        )
    if numerator.entity_scope not in STANDALONE:
        return _missing_ratio(
            template,
            ratio_code,
            "INCOMPATIBLE_SCOPE",
            f"{ratio_code} requires standalone COMPANY/BANK inputs.",
        )
    if numerator.comparison_role != "CURRENT" or denominator.comparison_role != "CURRENT":
        return _missing_ratio(
            template,
            ratio_code,
            "INCOMPATIBLE_PERIOD_CONTEXT",
            f"{ratio_code} requires CURRENT numerator and denominator facts.",
        )
    assert numerator.normalized_value is not None
    assert denominator.normalized_value is not None
    if denominator.normalized_value <= 0:
        return _missing_ratio(
            template,
            ratio_code,
            empty_denominator_reason,
            f"{denominator_code} is missing or not positive.",
        )
    value = numerator.normalized_value / denominator.normalized_value
    plausibility_issue = ratio_plausibility_issue(ratio_code, value)
    if plausibility_issue is not None:
        return _missing_ratio(template, ratio_code, "IMPLAUSIBLE_DERIVED_RATIO", plausibility_issue)
    return _ratio_fact(
        numerator,
        ratio_code,
        value,
        {
            numerator_code: str(numerator.normalized_value),
            denominator_code: str(denominator.normalized_value),
            "period_end": period_end.isoformat(),
        },
        formula,
        min(numerator.overall_certainty, denominator.overall_certainty) * 0.98,
        entity_scope=numerator.entity_scope,
    )


def derive_ratio_facts[TFiling](
    extracted_results: Sequence[tuple[TFiling, list[ExtractedFact]]],
    display_periods: Iterable[date] | None = None,
) -> list[tuple[TFiling, list[ExtractedFact]]]:
    """Fail-close source rows, then attach same-quarter ratios with exact lineage context."""

    sanitized_results = [
        (item, _sanitize_eps_selected([_sanitize_source_fact(fact) for fact in facts]))
        for item, facts in extracted_results
    ]
    index = _index_facts(sanitized_results)
    allowed = set(display_periods) if display_periods is not None else None
    derived_results: list[tuple[TFiling, list[ExtractedFact]]] = []
    for item, facts in sanitized_results:
        if not facts:
            derived_results.append((item, facts))
            continue
        template = facts[0]
        issuer_name = template.issuer_name
        period_end = template.period_end
        if allowed is not None and period_end not in allowed:
            derived_results.append((item, facts))
            continue
        extra = [
            _same_quarter_ratio(
                index=index,
                template=template,
                issuer_name=issuer_name,
                period_end=period_end,
                numerator_code="TOTAL_LIABILITIES",
                denominator_code="TOTAL_EQUITY",
                ratio_code="DEBT_TO_EQUITY",
                formula="TOTAL_LIABILITIES / TOTAL_EQUITY",
                empty_denominator_reason="ZERO_EQUITY",
            ),
            _same_quarter_ratio(
                index=index,
                template=template,
                issuer_name=issuer_name,
                period_end=period_end,
                numerator_code="PAT",
                denominator_code="TOTAL_EQUITY",
                ratio_code="ROE",
                formula="PAT / TOTAL_EQUITY",
                empty_denominator_reason="ZERO_EQUITY",
            ),
            _same_quarter_ratio(
                index=index,
                template=template,
                issuer_name=issuer_name,
                period_end=period_end,
                numerator_code="PAT",
                denominator_code="TOTAL_ASSETS",
                ratio_code="ROA",
                formula="PAT / TOTAL_ASSETS",
                empty_denominator_reason="NON_POSITIVE_DENOMINATOR",
            ),
            _same_quarter_ratio(
                index=index,
                template=template,
                issuer_name=issuer_name,
                period_end=period_end,
                numerator_code="PAT",
                denominator_code="TOP_LINE",
                ratio_code="NPM",
                formula="PAT / TOP_LINE",
                empty_denominator_reason="NON_POSITIVE_DENOMINATOR",
            ),
        ]
        derived_results.append((item, [*facts, *extra]))
    return derived_results
