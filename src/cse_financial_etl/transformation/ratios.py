from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact

ACCEPTED = {"EXTRACTED", "EXTRACTED_DERIVED"}


def _index_facts(
    facts_by_filing: Iterable[tuple[object, list[ExtractedFact]]],
) -> dict[tuple[str, date, str], ExtractedFact]:
    return {
        (fact.issuer_name, fact.period_end, fact.metric_code): fact
        for _item, facts in facts_by_filing
        for fact in facts
    }


def _accepted(fact: ExtractedFact | None) -> ExtractedFact | None:
    if fact is None or fact.status not in ACCEPTED or fact.normalized_value is None:
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
) -> ExtractedFact:
    band = "HIGH" if certainty >= 0.9 else "MEDIUM" if certainty >= 0.75 else "LOW"
    return replace(
        template,
        metric_code=metric_code,
        metric_type="RATIO",
        raw_text=None,
        raw_value=None,
        normalized_value=value,
        scale_factor=1,
        source_line=formula,
        unit_source_text="DERIVED_RATIO",
        confidence=band,
        status="EXTRACTED_DERIVED",
        raw_label=metric_code,
        extraction_method="DETERMINISTIC_DERIVATION",
        semantic_model="rule",
        semantic_confidence=1.0,
        validation_confidence=0.98,
        overall_certainty=round(certainty, 4),
        certainty_band=band,
        duration_months=3,
        validation_status="PASSED",
        review_status="APPROVED",
        evidence_json=json.dumps(
            {"formula": formula, "inputs": inputs, "derived_value": str(value)},
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
    """Compute a ratio from the same filing period only. No prior-quarter history."""

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
    assert numerator.normalized_value is not None
    assert denominator.normalized_value is not None
    if denominator.normalized_value <= 0:
        return _missing_ratio(
            template,
            ratio_code,
            empty_denominator_reason,
            f"{denominator_code} is missing or not positive.",
        )
    return _ratio_fact(
        template,
        ratio_code,
        numerator.normalized_value / denominator.normalized_value,
        {
            numerator_code: str(numerator.normalized_value),
            denominator_code: str(denominator.normalized_value),
            "period_end": period_end.isoformat(),
        },
        formula,
        min(numerator.overall_certainty, denominator.overall_certainty) * 0.98,
    )


def derive_ratio_facts[TFiling](
    extracted_results: Sequence[tuple[TFiling, list[ExtractedFact]]],
    display_periods: Iterable[date] | None = None,
) -> list[tuple[TFiling, list[ExtractedFact]]]:
    """Attach same-quarter leverage and profitability ratios with lineage."""

    index = _index_facts(extracted_results)
    allowed = set(display_periods) if display_periods is not None else None
    derived_results: list[tuple[TFiling, list[ExtractedFact]]] = []
    for item, facts in extracted_results:
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
