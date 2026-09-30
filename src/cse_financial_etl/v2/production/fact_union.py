"""Union V1 baseline SourceFacts with native V2 SourceFacts.

Policy (production selection, not guessing):
- Both agree → keep one (prefer the stronger PDF pointer; tag V1_V2_AGREE).
- Only V1 → preserve unless V2 already withheld it as invalid.
- V2 has strictly stronger PDF evidence and a different value → V2 replaces V1.
- Conflict without a decisive evidence gap → quarantine both (WITHHELD).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    PublicationStatus,
)
from cse_financial_etl.v2.contracts.facts import SourceFact

FactKey = tuple[str, date, EntityScope, ComparisonRole, int | None]
PER_SHARE_METRICS = frozenset({"EPS_BASIC", "EPS_DILUTED", "NAVPS"})
SCALE_CONFLICT_RATIO = Decimal("50")


def fact_key(fact: SourceFact) -> FactKey:
    return (
        fact.metric_code,
        fact.period_end,
        fact.entity_scope,
        fact.comparison_role,
        fact.duration_months,
    )


def values_agree(left: Decimal, right: Decimal, *, metric_code: str = "") -> bool:
    if left == right:
        return True
    difference = abs(left - right)
    scale = max(abs(left), abs(right), Decimal("1"))
    if metric_code in PER_SHARE_METRICS:
        return difference <= max(Decimal("0.005"), scale * Decimal("0.000001"))
    return difference <= max(Decimal("0.5"), scale * Decimal("0.000001"))


def scale_conflict(left: Decimal, right: Decimal) -> bool:
    """V2 is not stronger evidence when the values differ by a unit-scale jump."""

    left_abs = abs(left)
    right_abs = abs(right)
    if left_abs == 0 or right_abs == 0:
        return left_abs != right_abs and max(left_abs, right_abs) >= Decimal("1")
    return max(left_abs, right_abs) / min(left_abs, right_abs) >= SCALE_CONFLICT_RATIO


def evidence_strength(fact: SourceFact) -> int:
    """PDF-pointer strength. V2 is not automatically stronger than V1."""

    score = 0
    ref = fact.source_ref
    if ref.bbox is not None:
        score += 3
    if ref.raw_text:
        score += 1
    if ref.page_number >= 1 and "V1_PAGE_DEFAULT" not in fact.reason_codes:
        score += 1
    if fact.currency:
        score += 1
    if fact.duration_months in {None, 3}:
        score += 1
    if ref.parser_name.startswith("v2."):
        score += 1
    return score


def union_source_facts(
    v2_facts: tuple[SourceFact, ...] | list[SourceFact],
    v1_facts: tuple[SourceFact, ...] | list[SourceFact],
) -> tuple[SourceFact, ...]:
    """Merge native V2 facts with V1 baseline facts under the preserve-V1 rule."""

    v2_by_key: dict[FactKey, list[SourceFact]] = {}
    for fact in v2_facts:
        v2_by_key.setdefault(fact_key(fact), []).append(fact)
    v1_by_key: dict[FactKey, list[SourceFact]] = {}
    for fact in v1_facts:
        v1_by_key.setdefault(fact_key(fact), []).append(fact)

    merged: list[SourceFact] = []
    seen: set[FactKey] = set()
    for key in (*v2_by_key, *v1_by_key):
        if key in seen:
            continue
        seen.add(key)
        v2_group = v2_by_key.get(key, [])
        v1_group = v1_by_key.get(key, [])
        merged.extend(_union_key(v2_group, v1_group))
    return tuple(merged)


def _union_key(
    v2_group: list[SourceFact],
    v1_group: list[SourceFact],
) -> list[SourceFact]:
    v2_best = _best(v2_group)
    v1_best = _best(v1_group)
    if v1_best is None:
        return [
            _annotate(fact, "V2_RECOVERY")
            for fact in v2_group
        ]
    if v2_best is None:
        return [_annotate(v1_best, "V1_BASELINE_PRESERVED")]

    v2_invalid = v2_best.publication_status is PublicationStatus.WITHHELD
    if v2_invalid and not v1_group:
        return [_annotate(v2_best, "V2_ONLY_WITHHELD")]

    if values_agree(
        v1_best.normalized_value,
        v2_best.normalized_value,
        metric_code=v1_best.metric_code,
    ):
        eligible = [
            fact
            for fact in (v1_best, v2_best)
            if fact.publication_status is PublicationStatus.ELIGIBLE
        ]
        keeper = max(eligible, key=evidence_strength) if eligible else v1_best
        return [_annotate(keeper, "V1_V2_AGREE")]

    if v2_best.publication_status is PublicationStatus.WITHHELD:
        return [_annotate(v1_best, "V1_BASELINE_PRESERVED")]

    if scale_conflict(v1_best.normalized_value, v2_best.normalized_value):
        return [_annotate(v1_best, "V1_BASELINE_PRESERVED")]

    v1_has_pdf_pointer = v1_best.source_ref.bbox is not None
    v2_stronger = evidence_strength(v2_best) >= evidence_strength(v1_best) + 2
    v2_publishable = v2_best.publication_status is PublicationStatus.ELIGIBLE
    if v2_stronger and v2_publishable and not v2_invalid and v1_has_pdf_pointer:
        return [
            _annotate(v2_best, "V2_SUPERSEDES_V1"),
            _annotate(
                v1_best.model_copy(
                    update={"publication_status": PublicationStatus.WITHHELD}
                ),
                "V1_SUPERSEDED",
            ),
        ]

    return [
        _annotate(
            v1_best.model_copy(update={"publication_status": PublicationStatus.WITHHELD}),
            "CONFLICT_UNRESOLVED",
        ),
        _annotate(
            v2_best.model_copy(update={"publication_status": PublicationStatus.WITHHELD}),
            "CONFLICT_UNRESOLVED",
        ),
    ]


def _best(facts: list[SourceFact]) -> SourceFact | None:
    if not facts:
        return None
    eligible = [fact for fact in facts if fact.publication_status is PublicationStatus.ELIGIBLE]
    pool = eligible or facts
    return max(pool, key=evidence_strength)


def _annotate(fact: SourceFact, code: str) -> SourceFact:
    reasons = list(fact.reason_codes)
    if code not in reasons:
        reasons.append(code)
    return fact.model_copy(update={"reason_codes": tuple(reasons)})
