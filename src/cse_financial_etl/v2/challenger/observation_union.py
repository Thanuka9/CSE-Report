"""Union V1 physical observations into V2 FactCandidates (challenger-only).

V1 published workbook values never enter this path. Observations stay
non-publishable until V2 resolver/validation admits them with evidence.
"""

from __future__ import annotations

import re
from decimal import Decimal

from cse_financial_etl.v2.challenger.models import V1SourceObservation
from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import MatchKind, ResolutionStatus, StatementType
from cse_financial_etl.v2.contracts.facts import FactCandidate
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher
from cse_financial_etl.v2.taxonomy.registry import load_registry

_NOTE_INDEX_TEXT = re.compile(r"^-?\d{1,2}$")
_PER_SHARE = frozenset({"EPS_BASIC", "EPS_DILUTED", "NAVPS"})
# Share counts / stated capital masquerading as EPS are typically millions+.
_EPS_SHARE_COUNT_MIN = Decimal("1000")


def looks_like_note_index(*, raw_text: str | None, raw_value: Decimal | None) -> bool:
    """True for bare note-column integers (e.g. '4', '6') — not statement amounts."""

    if raw_value is None:
        return False
    text = (raw_text or "").strip()
    # Prefer the cell token after ' | ' when bridge concatenates label|value.
    if " | " in text:
        text = text.rsplit(" | ", 1)[-1].strip()
    text = text.replace(",", "")
    if not _NOTE_INDEX_TEXT.fullmatch(text):
        return False
    try:
        n = int(text)
    except ValueError:
        return False
    return 1 <= abs(n) <= 99 and raw_value == Decimal(n)


def looks_like_share_count_not_eps(*, metric_code: str | None, raw_value: Decimal | None) -> bool:
    """Reject share-count / stated-capital magnitudes on per-share metrics."""

    if metric_code not in {"EPS_BASIC", "EPS_DILUTED"} or raw_value is None:
        return False
    return abs(raw_value) >= _EPS_SHARE_COUNT_MIN


def observations_to_discovery_candidates(
    observations: tuple[V1SourceObservation, ...],
    *,
    matcher: RegistryMatcher | None = None,
) -> tuple[FactCandidate, ...]:
    """Map anchored observations to FactCandidates for union with V2.

    Concept may be suggested from the row label given statement type. Entity /
    period / unit come only from the observation (filled by the header bridge
    when source evidence exists). CHANGES_IN_EQUITY hints never resolve PAT.
    Note-index cells and share-count-as-EPS never become target concepts.
    """

    matcher = matcher or RegistryMatcher(load_registry())
    out: list[FactCandidate] = []
    for obs in observations:
        if obs.source_ref.bbox is None:
            continue
        statement_type = _statement_type(obs.statement_hint)
        concept = ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)
        reasons = list(obs.reason_codes)
        note_index = looks_like_note_index(raw_text=obs.raw_text or obs.source_ref.raw_text, raw_value=obs.raw_value)
        if note_index:
            reasons.append("NOTE_COLUMN_OR_INDEX")
        if obs.row_label and statement_type is not StatementType.CHANGES_IN_EQUITY and not note_index:
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
                if hits[0].metric_code == "PAT" and statement_type is not StatementType.INCOME_STATEMENT:
                    concept = ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)
                elif looks_like_share_count_not_eps(
                    metric_code=hits[0].metric_code, raw_value=obs.raw_value
                ):
                    reasons.append("SHARE_COUNT_NOT_EPS")
                    concept = ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)
                else:
                    concept = hits[0]
        if obs.discovery_only and "DISCOVERY_ONLY" not in reasons:
            reasons.append("DISCOVERY_ONLY")
        reasons.append("V1_OBSERVATION_UNION")
        # Prefer per-share unit when concept is per-share.
        unit_dimension = obs.unit_dimension
        monetary_scale = obs.monetary_scale
        if concept.metric_code in _PER_SHARE:
            from cse_financial_etl.v2.contracts.enums import UnitDimension

            unit_dimension = UnitDimension.PER_SHARE
            if monetary_scale is not None and monetary_scale >= 1000:
                monetary_scale = None
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
                    else (
                        ResolutionStatus.NOT_APPLICABLE
                        if obs.statement_hint == "BALANCE_SHEET" and obs.period_end is not None
                        else ResolutionStatus.UNRESOLVED
                    )
                ),
                comparison_role=obs.comparison_role,
                comparison_status=(
                    ResolutionStatus.RESOLVED
                    if obs.comparison_role is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                currency=obs.currency,
                monetary_scale=monetary_scale,
                unit_dimension=unit_dimension,
                unit_status=(
                    ResolutionStatus.RESOLVED
                    if unit_dimension is not None
                    else ResolutionStatus.UNRESOLVED
                ),
                raw_value=obs.raw_value,
                source_ref=obs.source_ref,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )
    return tuple(out)


def union_candidates(
    primary: tuple[FactCandidate, ...],
    extra: tuple[FactCandidate, ...],
) -> tuple[FactCandidate, ...]:
    """Deduplicate by source identity; upgrade V2 only when bridge corrects context.

    Prefer a V1-bridged candidate over V2 for the same PDF cell when the bridge
    supplies a *different* evidenced duration (quarter vs period-ended) or fills
    missing entity/period/unit. Do not replace an equally contextualized V2
    candidate — that caused false value swaps on multi-column statements.
    """

    chosen: dict[tuple[object, ...], FactCandidate] = {}
    order: list[tuple[object, ...]] = []

    def cell_keys(candidate: FactCandidate) -> tuple[tuple[object, ...], ...]:
        metric = None if candidate.concept is None else candidate.concept.metric_code
        bbox = candidate.source_ref.bbox
        rounded = None
        if bbox is not None:
            rounded = tuple(round(float(x), 1) for x in bbox)
        strict = (
            candidate.source_ref.source_sha256,
            candidate.source_ref.page_number,
            rounded,
            str(candidate.raw_value),
            metric,
        )
        loose = (
            "loose",
            candidate.source_ref.source_sha256,
            candidate.source_ref.page_number,
            str(candidate.raw_value),
            metric,
        )
        return (strict, loose)

    for candidate in (*primary, *extra):
        keys = cell_keys(candidate)
        existing = None
        for key in keys:
            if key in chosen:
                existing = chosen[key]
                break
        if existing is None:
            for key in keys:
                chosen[key] = candidate
                if key not in order:
                    order.append(key)
            continue
        if _should_replace(existing, candidate):
            for key in cell_keys(candidate):
                chosen[key] = candidate
            for key in cell_keys(existing):
                chosen[key] = candidate

    # Deduplicate by physical cell identity — not candidate_id. V2 can assign the
    # same cell_id to a note-index glyph and the adjacent amount; dropping by id
    # deleted correct revenues (JAT/HAYLEYS) and left the note as the only ELIGIBLE.
    seen_cells: set[tuple[object, ...]] = set()
    out: list[FactCandidate] = []
    for key in order:
        cand = chosen.get(key)
        if cand is None:
            continue
        cell_identity = cell_keys(cand)[0]
        if cell_identity in seen_cells:
            continue
        seen_cells.add(cell_identity)
        out.append(cand)
    return tuple(out)


def _is_bridged(candidate: FactCandidate) -> bool:
    return "CONTEXT_BRIDGED_SOURCE_OWNED" in (candidate.reason_codes or ())


def _should_replace(current: FactCandidate, challenger: FactCandidate) -> bool:
    """Return True when challenger has corrective source-owned context vs current.

    Preserve V2 when the bridge is silent, incomplete, or weaker. Demote a V2
    quarter binding only when bridged headers mark the *same cell* cumulative.
    """

    if not _is_bridged(challenger):
        return False
    # Never let a note-index / share-count challenger displace a V2 amount.
    metric = None if challenger.concept is None else challenger.concept.metric_code
    if looks_like_note_index(
        raw_text=challenger.source_ref.raw_text, raw_value=challenger.raw_value
    ):
        return False
    if looks_like_share_count_not_eps(metric_code=metric, raw_value=challenger.raw_value):
        return False
    if _is_bridged(current) and _context_richness(challenger) <= _context_richness(current):
        return False
    # Bridged fills missing required dimensions.
    if current.entity_scope is None and challenger.entity_scope is not None:
        return True
    if current.period_end is None and challenger.period_end is not None:
        return True
    if current.unit_dimension is None and challenger.unit_dimension is not None:
        return True
    # Only demote a V2 exact-quarter binding when V1 headers mark the same cell
    # as cumulative/period-ended (duration None). Do not trust a bridged non-3
    # duration over V2's quarter — V1 headers can mis-bind Year/Period labels.
    return bool(current.duration_months == 3 and challenger.duration_months is None and "FLOW_DURATION_UNRESOLVED_OR_CUMULATIVE" in (challenger.reason_codes or ()))


def _context_richness(candidate: FactCandidate) -> int:
    score = 0
    if candidate.concept_status is ResolutionStatus.RESOLVED:
        score += 1
    if candidate.entity_status is ResolutionStatus.RESOLVED:
        score += 1
    if candidate.period_status is ResolutionStatus.RESOLVED:
        score += 1
    if candidate.unit_status is ResolutionStatus.RESOLVED:
        score += 1
    if candidate.comparison_status is ResolutionStatus.RESOLVED:
        score += 1
    if _is_bridged(candidate):
        score += 2
    return score


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
