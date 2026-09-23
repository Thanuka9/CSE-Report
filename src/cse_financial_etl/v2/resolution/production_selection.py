"""Production snapshot selection. Does not mutate source extraction."""

from __future__ import annotations

from datetime import date

from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    ProductionSelectionStatus,
    PublicationStatus,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact, SourceFact

_ENTITY_EQUIVALENTS: dict[EntityScope, frozenset[EntityScope]] = {
    EntityScope.COMPANY: frozenset({EntityScope.COMPANY, EntityScope.SEPARATE}),
    EntityScope.SEPARATE: frozenset({EntityScope.COMPANY, EntityScope.SEPARATE}),
    EntityScope.GROUP: frozenset({EntityScope.GROUP, EntityScope.CONSOLIDATED}),
    EntityScope.CONSOLIDATED: frozenset({EntityScope.GROUP, EntityScope.CONSOLIDATED}),
    EntityScope.BANK: frozenset({EntityScope.BANK}),
}


def entity_matches(actual: EntityScope, expected: EntityScope) -> bool:
    return actual in _ENTITY_EQUIVALENTS.get(expected, frozenset({expected}))


def select_pipeline_facts[TFact: SourceFact | DerivedFact](
    facts: tuple[TFact, ...] | list[TFact],
    *,
    period_end: date | None,
    expected_entity: EntityScope | None,
) -> tuple[TFact, ...]:
    """Keep current-period eligible facts for the production snapshot query.

    If the requested entity is absent among eligible facts, the snapshot is
    empty. GROUP is never forwarded as a COMPANY or BANK substitute.
    """

    eligible = [
        fact
        for fact in facts
        if fact.publication_status is PublicationStatus.ELIGIBLE
        and fact.comparison_role is ComparisonRole.CURRENT
        and (period_end is None or fact.period_end == period_end)
        and (fact.duration_months is None or fact.duration_months == 3)
    ]
    if expected_entity is not None:
        matching = [fact for fact in eligible if entity_matches(fact.entity_scope, expected_entity)]
        if not matching:
            return ()
        eligible = matching
    return _unique_by_metric(eligible)


def production_selection_outcome(
    fact: SourceFact | None,
    *,
    expected_entity: EntityScope | None,
    period_end: date | None,
    selected_ids: set[str],
) -> tuple[bool | None, ProductionSelectionStatus, str | None]:
    """Describe selector outcome without treating publication as selection."""

    if expected_entity is None and period_end is None:
        return None, ProductionSelectionStatus.NOT_APPLICABLE, None
    if fact is None:
        return False, ProductionSelectionStatus.NOT_SELECTED, "SOURCE_FACT_NOT_CREATED"
    if fact.fact_id in selected_ids:
        return True, ProductionSelectionStatus.SELECTED, "SELECTED"
    if fact.publication_status is PublicationStatus.WITHHELD:
        return False, ProductionSelectionStatus.NOT_SELECTED, "PUBLICATION_WITHHELD"
    if fact.comparison_role is not ComparisonRole.CURRENT:
        return False, ProductionSelectionStatus.NOT_SELECTED, "COMPARATIVE_ROLE"
    if period_end is not None and fact.period_end != period_end:
        return False, ProductionSelectionStatus.NOT_SELECTED, "PERIOD_MISMATCH"
    if fact.duration_months not in {None, 3}:
        return False, ProductionSelectionStatus.NOT_SELECTED, "EXACT_QUARTER_NOT_REPORTED"
    if expected_entity is not None and not entity_matches(fact.entity_scope, expected_entity):
        return False, ProductionSelectionStatus.NOT_SELECTED, "ENTITY_SCOPE_MISMATCH"
    return False, ProductionSelectionStatus.NOT_SELECTED, "DUPLICATE_METRIC"


def _unique_by_metric[TFact: SourceFact | DerivedFact](facts: list[TFact]) -> tuple[TFact, ...]:
    chosen: dict[str, TFact] = {}
    for fact in facts:
        existing = chosen.get(fact.metric_code)
        if existing is None or _fact_rank(fact) < _fact_rank(existing):
            chosen[fact.metric_code] = fact
    return tuple(chosen[code] for code in sorted(chosen))


def _fact_rank(fact: SourceFact | DerivedFact) -> tuple[int, int, int, int, int, str]:
    """Prefer primary statement amounts over early highlight cards in Rs Mn/Bn."""

    scale = getattr(fact, "source_scale", None)
    try:
        scale_val = abs(float(scale)) if scale is not None else 1.0
    except (TypeError, ValueError):
        scale_val = 1.0
    try:
        raw = abs(float(getattr(fact, "raw_value", 0) or 0))
    except (TypeError, ValueError):
        raw = 0.0
    try:
        norm = abs(float(getattr(fact, "normalized_value", 0) or 0))
    except (TypeError, ValueError):
        norm = 0.0

    # Natural currency units beat '000 / million / billion summary scales.
    scale_penalty = 0 if scale_val == 1.0 else 1
    # Among scaled highlights, prefer smaller scale distortion (Rs'000 over Bn).
    scale_magnitude = 0 if scale_val == 1.0 else int(scale_val)

    metric = getattr(fact, "metric_code", "") or ""
    unit = getattr(fact, "unit_dimension", None)
    per_share = metric in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"} or (
        unit is not None and "PER_SHARE" in str(unit)
    )
    # NAVPS/EPS of tens of millions are mis-bound absolute cells, not per-share.
    per_share_implausible = 1 if per_share and norm > 10_000 else 0

    page = getattr(getattr(fact, "source_ref", None), "page_number", 10**6) or 10**6
    if scale_val == 1.0 and not per_share:
        # Absolute monetary: prefer larger natural-scale statement totals.
        magnitude_key = -int(min(norm, 10**15))
        page_key = int(page)
    elif scale_val == 1.0 and per_share:
        # Prefer plausible per-share magnitudes (0.09 beats 0.0003; 3.46 beats 1.46).
        magnitude_key = -int(min(norm * 1_000_000, 10**15))
        page_key = int(page)
    else:
        magnitude_key = -int(min(raw, 10**15))
        page_key = int(page)

    return (
        scale_penalty,
        per_share_implausible,
        scale_magnitude,
        magnitude_key,
        page_key,
        fact.fact_id,
    )
