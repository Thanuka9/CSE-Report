"""Validation and derived-fact boundary over proven V1 ratio math."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.facts.derived_facts import compute_quarter_ratios
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    FactKind,
    PublicationStatus,
    ReviewStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact

FLOW_PUBLICATION_CODES = frozenset(
    {"PAT", "PBT", "OPERATING_PROFIT", "TOP_LINE", "EPS_BASIC", "EPS_DILUTED"}
)


def validate_source_facts(facts: tuple[SourceFact, ...]) -> tuple[SourceFact, ...]:
    by_key = {
        (fact.issuer_id, fact.metric_code, fact.period_end, fact.entity_scope): fact
        for fact in facts
    }
    validated: list[SourceFact] = []
    for fact in facts:
        reasons = list(fact.reason_codes)
        status = ValidationStatus.PASSED
        publication = fact.publication_status
        if fact.metric_code in FLOW_PUBLICATION_CODES and fact.duration_months != 3:
            status = ValidationStatus.FAILED
            publication = PublicationStatus.WITHHELD
            reasons.append("Q4_OR_CUMULATIVE_FLOW_BLOCKED")
        if fact.metric_code == "TOTAL_LIABILITIES":
            # Explicit source only. Assets - Equity is a signal, never a published source.
            assets = by_key.get(
                (fact.issuer_id, "TOTAL_ASSETS", fact.period_end, fact.entity_scope)
            )
            equity = by_key.get(
                (fact.issuer_id, "TOTAL_EQUITY", fact.period_end, fact.entity_scope)
            )
            if assets and equity:
                implied = assets.normalized_value - equity.normalized_value
                if fact.normalized_value != implied:
                    reasons.append("BALANCE_SHEET_RECONCILIATION_SIGNAL")
        validated.append(
            fact.model_copy(
                update={
                    "validation_status": status,
                    "publication_status": publication,
                    "reason_codes": tuple(dict.fromkeys(reasons)),
                }
            )
        )
    return tuple(validated)


def derive_facts(facts: tuple[SourceFact, ...]) -> tuple[DerivedFact, ...]:
    derived: list[DerivedFact] = []
    groups: dict[tuple[str, object, EntityScope], list[SourceFact]] = {}
    for fact in facts:
        if fact.validation_status is not ValidationStatus.PASSED:
            continue
        if fact.publication_status is PublicationStatus.WITHHELD:
            continue
        groups.setdefault((fact.issuer_id, fact.period_end, fact.entity_scope), []).append(fact)
    for (issuer_id, period_end, entity_scope), group in groups.items():
        by_code = {item.metric_code: item for item in group}
        diluted = by_code.get("EPS_DILUTED")
        basic = by_code.get("EPS_BASIC")
        selected = diluted or basic
        if selected is not None:
            derived.append(
                DerivedFact(
                    fact_id=f"{selected.fact_id}-eps-selected",
                    issuer_id=issuer_id,
                    metric_code="EPS_SELECTED",
                    formula_id="eps_selected.diluted_else_basic",
                    input_fact_ids=(selected.fact_id,),
                    normalized_value=selected.normalized_value,
                    entity_scope=entity_scope,
                    period_end=selected.period_end,
                    duration_months=selected.duration_months,
                    comparison_role=selected.comparison_role,
                    unit_dimension=UnitDimension.PER_SHARE,
                    validation_status=ValidationStatus.PASSED,
                    review_status=ReviewStatus.REVIEW,
                    publication_status=PublicationStatus.ELIGIBLE,
                )
            )
        ratios = compute_quarter_ratios(
            pat=_value(by_code.get("PAT")),
            equity=_value(by_code.get("TOTAL_EQUITY")),
            assets=_value(by_code.get("TOTAL_ASSETS")),
            liabilities=_value(by_code.get("TOTAL_LIABILITIES")),
            top_line=_value(by_code.get("TOP_LINE")),
        )
        mapping = {
            "DEBT_TO_EQUITY": ("LIABILITIES_TO_EQUITY", "liabilities_over_equity"),
            "ROE": ("ROE", "pat_over_equity"),
            "ROA": ("ROA", "pat_over_assets"),
            "NPM": ("NPM", "pat_over_top_line"),
        }
        for ratio in ratios:
            if ratio.value is None:
                continue
            metric_code, formula_id = mapping[ratio.code]
            needed = {
                "LIABILITIES_TO_EQUITY": ("TOTAL_LIABILITIES", "TOTAL_EQUITY"),
                "ROE": ("PAT", "TOTAL_EQUITY"),
                "ROA": ("PAT", "TOTAL_ASSETS"),
                "NPM": ("PAT", "TOP_LINE"),
            }[metric_code]
            inputs = tuple(by_code[code].fact_id for code in needed if code in by_code)
            if len(inputs) != len(needed):
                continue
            derived.append(
                DerivedFact(
                    fact_id=f"{issuer_id}-{metric_code}-{period_end}",
                    issuer_id=issuer_id,
                    metric_code=metric_code,
                    formula_id=formula_id,
                    input_fact_ids=inputs,
                    normalized_value=ratio.value,
                    entity_scope=entity_scope,
                    period_end=group[0].period_end,
                    duration_months=3,
                    comparison_role=ComparisonRole.CURRENT,
                    unit_dimension=UnitDimension.RATIO,
                    validation_status=ValidationStatus.PASSED,
                    review_status=ReviewStatus.REVIEW,
                    publication_status=PublicationStatus.ELIGIBLE,
                )
            )
    assert all(item.fact_kind is FactKind.DERIVED for item in derived)
    return tuple(derived)


def _value(fact: SourceFact | None) -> Decimal | None:
    return None if fact is None else fact.normalized_value
