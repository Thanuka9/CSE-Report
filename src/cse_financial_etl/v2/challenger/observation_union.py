"""Union V1 physical observations into V2 FactCandidates (challenger-only).

V1 published workbook values never enter this path. Observations stay
non-publishable until V2 resolver/validation admits them with evidence.
"""

from __future__ import annotations

from cse_financial_etl.v2.challenger.models import V1SourceObservation
from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import MatchKind, ResolutionStatus, StatementType
from cse_financial_etl.v2.contracts.facts import FactCandidate
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher
from cse_financial_etl.v2.taxonomy.registry import load_registry


def observations_to_discovery_candidates(
    observations: tuple[V1SourceObservation, ...],
    *,
    matcher: RegistryMatcher | None = None,
) -> tuple[FactCandidate, ...]:
    """Map anchored observations to unresolved FactCandidates for trace/union.

    Concept may be suggested from the row label; entity/period/unit stay
    unresolved unless already present on the observation (they are not filled
    from issuer identity here). CHANGES_IN_EQUITY hints never resolve PAT.
    """

    matcher = matcher or RegistryMatcher(load_registry())
    registry = matcher.registry
    out: list[FactCandidate] = []
    for obs in observations:
        if obs.source_ref.bbox is None:
            continue
        statement_type = _statement_type(obs.statement_hint)
        concept = ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)
        if obs.row_label and statement_type is not StatementType.CHANGES_IN_EQUITY:
            from cse_financial_etl.v2.contracts.statement import StatementRow

            hits = matcher.candidates(
                StatementRow(
                    row_id=f"{obs.table_id}-r{obs.row_index}",
                    raw_label=obs.row_label,
                    normalized_label=obs.row_label,
                ),
                statement_type=statement_type,
            )
            if hits and hits[0].metric_code:
                # PAT must not be taken from equity-statement rows even if label matches.
                if hits[0].metric_code == "PAT" and statement_type is not StatementType.INCOME_STATEMENT:
                    concept = ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)
                else:
                    concept = hits[0]
        reasons = list(obs.reason_codes)
        if "DISCOVERY_ONLY" not in reasons:
            reasons.append("DISCOVERY_ONLY")
        reasons.append("V1_OBSERVATION_UNION")
        out.append(
            FactCandidate(
                candidate_id=f"v1obs-{obs.observation_id}-cand",
                statement_id=obs.table_id,
                cell_id=f"{obs.table_id}-r{obs.row_index}-c{obs.col_index}",
                row_id=f"{obs.table_id}-r{obs.row_index}",
                column_id=f"{obs.table_id}-c{obs.col_index}",
                concept=concept,
                concept_status=(
                    ResolutionStatus.RESOLVED
                    if concept.metric_code is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                entity_scope=obs.entity_scope,
                entity_status=(
                    ResolutionStatus.RESOLVED
                    if obs.entity_scope is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                period_end=obs.period_end,
                period_status=(
                    ResolutionStatus.RESOLVED
                    if obs.period_end is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                duration_months=obs.duration_months,
                duration_status=(
                    ResolutionStatus.RESOLVED
                    if obs.duration_months is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                comparison_role=obs.comparison_role,
                comparison_status=(
                    ResolutionStatus.RESOLVED
                    if obs.comparison_role is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                currency=obs.currency,
                monetary_scale=obs.monetary_scale,
                unit_dimension=obs.unit_dimension,
                unit_status=(
                    ResolutionStatus.RESOLVED
                    if obs.unit_dimension is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                raw_value=obs.raw_value,
                source_ref=obs.source_ref,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )
    del registry
    return tuple(out)


def union_candidates(
    primary: tuple[FactCandidate, ...],
    extra: tuple[FactCandidate, ...],
) -> tuple[FactCandidate, ...]:
    """Deduplicate by source identity; keep conflicts visible as separate candidates."""

    seen: set[tuple[object, ...]] = set()
    out: list[FactCandidate] = []
    for candidate in (*primary, *extra):
        key = (
            candidate.source_ref.source_sha256,
            candidate.source_ref.page_number,
            candidate.source_ref.bbox,
            str(candidate.raw_value),
            None if candidate.concept is None else candidate.concept.metric_code,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return tuple(out)


def _statement_type(hint: str | None) -> StatementType:
    if hint == "INCOME_STATEMENT":
        return StatementType.INCOME_STATEMENT
    if hint == "BALANCE_SHEET":
        return StatementType.BALANCE_SHEET
    if hint == "CASH_FLOW":
        return StatementType.CASH_FLOW
    if hint == "CHANGES_IN_EQUITY":
        return StatementType.CHANGES_IN_EQUITY
    if hint == "EPS_NOTE":
        return StatementType.EPS_NOTE
    return StatementType.OTHER_FINANCIAL_STATEMENT
