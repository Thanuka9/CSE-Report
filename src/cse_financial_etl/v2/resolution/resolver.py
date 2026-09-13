"""Build FactCandidates and resolve SourceFacts without assuming missing context."""

from __future__ import annotations

import re
from decimal import Decimal

from cse_financial_etl.v2.contracts.concepts import ConceptCandidate
from cse_financial_etl.v2.contracts.enums import (
    AccountingRegime,
    ComparisonRole,
    EntityScope,
    MatchKind,
    PeriodBehavior,
    PublicationStatus,
    ResolutionStatus,
    ReviewStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import FactCandidate, SourceFact
from cse_financial_etl.v2.contracts.statement import (
    CanonicalStatement,
    StatementCell,
    StatementColumn,
    StatementRow,
)
from cse_financial_etl.v2.taxonomy.matcher import RegistryMatcher
from cse_financial_etl.v2.taxonomy.registry import ConceptRegistry, load_registry, normalize_label

FLOW_CODES = frozenset({"PAT", "PBT", "OPERATING_PROFIT", "TOP_LINE", "EPS_BASIC", "EPS_DILUTED"})
_ROW_LABEL_PREFIX = re.compile(r"\s+[\d(]")


def _status(value: object) -> ResolutionStatus:
    return ResolutionStatus.RESOLVED if value is not None else ResolutionStatus.UNRESOLVED


def build_candidates(
    statement: CanonicalStatement,
    *,
    matcher: RegistryMatcher | None = None,
    accounting_regime: AccountingRegime | None = None,
) -> tuple[FactCandidate, ...]:
    matcher = matcher or RegistryMatcher()
    columns = {column.column_id: column for column in statement.columns}
    candidates: list[FactCandidate] = []
    for row in statement.rows:
        concepts = matcher.candidates(
            row,
            statement_type=statement.statement_type,
            accounting_regime=accounting_regime,
        )
        primary = (
            concepts[0]
            if concepts
            else ConceptCandidate(metric_code=None, match_kind=MatchKind.ABSTAIN)
        )
        for cell in row.cells:
            if cell.raw_text.strip().endswith("%"):
                continue
            column = columns[cell.column_id]
            candidates.append(_candidate(statement, row, column, cell, primary, concepts))
    return tuple(candidates)


def _candidate(
    statement: CanonicalStatement,
    row: StatementRow,
    column: StatementColumn,
    cell: StatementCell,
    concept: ConceptCandidate,
    all_concepts: list[ConceptCandidate],
) -> FactCandidate:
    ambiguous = (
        sum(1 for item in all_concepts if item.metric_code and item.match_kind != MatchKind.ABSTAIN)
        > 1
    )
    concept_status = (
        ResolutionStatus.UNRESOLVED
        if concept.metric_code is None or ambiguous
        else ResolutionStatus.RESOLVED
    )
    reasons: list[str] = []
    if concept_status is ResolutionStatus.UNRESOLVED:
        reasons.append("CONCEPT_UNRESOLVED" if not ambiguous else "AMBIGUOUS_CONCEPT")
    if column.entity_scope is None:
        reasons.append("ENTITY_NOT_RESOLVED")
    if column.period_end is None:
        reasons.append("PERIOD_NOT_RESOLVED")
    if column.unit_dimension is None:
        reasons.append("UNIT_NOT_RESOLVED")
    return FactCandidate(
        candidate_id=f"{cell.cell_id}-cand",
        statement_id=statement.statement_id,
        cell_id=cell.cell_id,
        row_id=row.row_id,
        column_id=column.column_id,
        concept=concept,
        concept_status=concept_status,
        entity_scope=column.entity_scope,
        entity_status=_status(column.entity_scope),
        period_end=column.period_end,
        period_status=_status(column.period_end),
        duration_months=column.duration_months,
        duration_status=_status(column.duration_months),
        comparison_role=column.comparison_role,
        comparison_status=_status(column.comparison_role),
        currency=column.currency,
        monetary_scale=column.monetary_scale,
        unit_dimension=column.unit_dimension,
        unit_status=_status(column.unit_dimension),
        raw_value=cell.parsed_numeric_value,
        source_ref=cell.source_ref,
        reason_codes=tuple(reasons),
    )


def resolve_source_facts(
    candidates: tuple[FactCandidate, ...],
    *,
    issuer_id: str,
    filing_version_id: str,
    registry: ConceptRegistry | None = None,
    expected_entity_scope: EntityScope | None = None,
) -> tuple[SourceFact, ...]:
    """Emit SourceFacts only when required source context is present. Never assume."""

    registry = registry or load_registry()
    facts: list[SourceFact] = []
    for candidate in candidates:
        if (
            candidate.raw_value is None
            or candidate.concept is None
            or candidate.concept.metric_code is None
        ):
            continue
        if candidate.concept_status is not ResolutionStatus.RESOLVED:
            continue
        if (
            candidate.entity_status is not ResolutionStatus.RESOLVED
            or candidate.entity_scope is None
        ):
            continue
        if candidate.period_status is not ResolutionStatus.RESOLVED or candidate.period_end is None:
            continue
        if (
            candidate.unit_status is not ResolutionStatus.RESOLVED
            or candidate.unit_dimension is None
        ):
            continue
        if expected_entity_scope is not None and candidate.entity_scope != expected_entity_scope:
            continue
        concept = registry.get(candidate.concept.metric_code)
        if (
            concept.unit_dimension is UnitDimension.MONETARY
            and candidate.unit_dimension is not UnitDimension.MONETARY
        ):
            continue
        duration = candidate.duration_months
        if concept.period_behavior in {PeriodBehavior.STOCK, PeriodBehavior.POINT_IN_TIME}:
            duration = None
        comparison = candidate.comparison_role or ComparisonRole.UNKNOWN
        reasons: list[str] = []
        publication = PublicationStatus.ELIGIBLE
        if concept.period_behavior is PeriodBehavior.FLOW:
            if duration != 3:
                publication = PublicationStatus.WITHHELD
                reasons.append("EXACT_QUARTER_NOT_REPORTED")
            if comparison is not ComparisonRole.CURRENT:
                publication = PublicationStatus.WITHHELD
                reasons.append("COMPARATIVE_ROLE")
        if candidate.concept.metric_code in FLOW_CODES and duration in {6, 9, 12}:
            publication = PublicationStatus.WITHHELD
            reasons.append("CUMULATIVE_ONLY")
        scale = candidate.monetary_scale or Decimal("1")
        if concept.unit_dimension is not UnitDimension.MONETARY:
            # Per-share / ratio facts must not inherit statement Rs/'000 scaling.
            scale = Decimal("1")
        normalized = (
            candidate.raw_value * scale
            if concept.unit_dimension is UnitDimension.MONETARY
            else candidate.raw_value
        )
        facts.append(
            SourceFact(
                fact_id=candidate.candidate_id.replace("-cand", "-fact"),
                filing_version_id=filing_version_id,
                statement_id=candidate.statement_id,
                cell_id=candidate.cell_id,
                issuer_id=issuer_id,
                metric_code=candidate.concept.metric_code,
                entity_scope=candidate.entity_scope,
                period_end=candidate.period_end,
                duration_months=duration,
                comparison_role=comparison,
                raw_value=candidate.raw_value,
                normalized_value=normalized,
                currency=candidate.currency,
                source_scale=scale,
                unit_dimension=candidate.unit_dimension,
                source_ref=candidate.source_ref,
                validation_status=ValidationStatus.NOT_VALIDATED,
                review_status=ReviewStatus.REVIEW,
                publication_status=publication,
                duration_status=(
                    ResolutionStatus.RESOLVED
                    if duration is not None
                    else ResolutionStatus.NOT_APPLICABLE
                ),
                reason_codes=tuple(reasons),
            )
        )
    return _withhold_conflicting_values(tuple(facts))


def _withhold_conflicting_values(facts: tuple[SourceFact, ...]) -> tuple[SourceFact, ...]:
    """Do not last-write-win when two current cells disagree on the same metric."""

    groups: dict[tuple[object, ...], list[SourceFact]] = {}
    for fact in facts:
        if fact.publication_status is not PublicationStatus.ELIGIBLE:
            continue
        key = (
            fact.statement_id,
            fact.metric_code,
            _conflict_row_label(fact),
            fact.entity_scope,
            fact.period_end,
            fact.duration_months,
            fact.comparison_role,
        )
        groups.setdefault(key, []).append(fact)
    conflict_ids = {
        member.fact_id
        for members in groups.values()
        if len({member.normalized_value for member in members}) > 1
        for member in members
    }
    if not conflict_ids:
        return facts
    updated: list[SourceFact] = []
    for fact in facts:
        if fact.fact_id not in conflict_ids:
            updated.append(fact)
            continue
        updated.append(
            fact.model_copy(
                update={
                    "publication_status": PublicationStatus.WITHHELD,
                    "reason_codes": (*fact.reason_codes, "CONFLICTING_SOURCE"),
                }
            )
        )
    return tuple(updated)


def _conflict_row_label(fact: SourceFact) -> str:
    """Account label only. Gross income and Interest income are not duplicates."""

    text = fact.source_ref.raw_text or ""
    match = _ROW_LABEL_PREFIX.search(text)
    head = text[: match.start()] if match is not None else text
    return normalize_label(head)
