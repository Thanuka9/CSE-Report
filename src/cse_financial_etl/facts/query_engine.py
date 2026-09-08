"""Query accepted ledger candidates for target metrics.

Absence statuses are metric-specific and describe what the search actually
found (audit finding 8). The query layer never claims the source omitted a
figure — ``SOURCE_CONFIRMED_NOT_REPORTED`` requires a reviewed evidence packet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from cse_financial_etl.contracts.eligibility import (
    COMPARATIVE_NOT_CURRENT,
    ENTITY_UNKNOWN,
    GROUP_CANNOT_SATISFY_COMPANY,
    PERIOD_UNKNOWN,
    UNIT_UNRESOLVED,
    YTD_CANNOT_SATISFY_3M,
    evaluate_eligibility,
)
from cse_financial_etl.domain.enums import MissingReason
from cse_financial_etl.facts.target_metrics import TargetQuery, default_queries
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry


@dataclass(frozen=True, slots=True)
class SearchTrace:
    """What was searched for an unresolved metric (carried to the review view)."""

    candidates_seen: int
    pages: tuple[int, ...]
    columns: tuple[str, ...]
    rejected_reasons: tuple[str, ...]
    unresolved_reasons: tuple[str, ...]
    recovery_attempted: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates_seen": self.candidates_seen,
            "pages": list(self.pages),
            "columns": list(self.columns),
            "rejected_reasons": list(self.rejected_reasons),
            "unresolved_reasons": list(self.unresolved_reasons),
            "recovery_attempted": self.recovery_attempted,
        }


@dataclass(frozen=True, slots=True)
class QueriedFact:
    metric_code: str
    concept: str
    entry: LedgerEntry | None
    status: str
    issue: str | None = None
    trace: SearchTrace | None = None
    eligibility_reasons: tuple[str, ...] = field(default_factory=tuple)


def query_target_facts(
    ledger: CandidateLedger,
    *,
    entity: str,
    period_end,
    target_duration: int = 3,
    recovery_attempted: bool = False,
) -> list[QueriedFact]:
    results: list[QueriedFact] = []
    period_s = period_end.isoformat() if hasattr(period_end, "isoformat") else str(period_end)
    for query in default_queries(entity=entity, period_end=period_end):
        results.append(
            _query_one(
                ledger,
                query,
                target_period_end=period_s,
                target_duration=target_duration,
                recovery_attempted=recovery_attempted,
            )
        )
    return results


def _query_one(
    ledger: CandidateLedger,
    query: TargetQuery,
    *,
    target_period_end: str,
    target_duration: int,
    recovery_attempted: bool,
) -> QueriedFact:
    family = _concept_family(query.concept)
    all_entries = [e for concept in family for e in ledger.for_concept(concept)]
    # Family order is a preference order: the first family member with an accepted,
    # eligible candidate wins (e.g. REVENUE before TOTAL_INCOME for TOP_LINE).
    accepted = [e for e in all_entries if e.status == "accepted" and e.normalized_value is not None]
    accepted.sort(key=lambda e: family.index(e.concept))
    duration = query.duration_months if query.duration_months is not None else target_duration
    eligible_accepted: list[tuple[LedgerEntry, tuple[str, ...]]] = []
    for entry in accepted:
        result = evaluate_eligibility(
            entry,
            required_entity=query.entity,
            target_duration=duration if query.duration_months is not None else None,
            target_period_end=target_period_end,
            concept=query.concept,
        )
        if result.eligible:
            eligible_accepted.append((entry, result.reasons))
    if eligible_accepted:
        first_concept = eligible_accepted[0][0].concept
        same_concept = [item for item in eligible_accepted if item[0].concept == first_concept]
        best, reasons = max(same_concept, key=lambda item: item[0].score)
        return QueriedFact(query.metric_code, best.concept, best, "EXTRACTED", None, eligibility_reasons=reasons)

    trace = _trace(all_entries, recovery_attempted)
    unresolved = [e for e in all_entries if e.status == "unresolved"]
    if unresolved:
        reasons = _reason_histogram(unresolved)
        primary = reasons[0] if reasons else "unresolved_after_arbiter"
        if primary == "AMBIGUOUS_EQUAL_SCORE":
            status = MissingReason.AMBIGUOUS_CANDIDATES
        elif primary.startswith(UNIT_UNRESOLVED) or primary.startswith("SCALE_UNRESOLVED"):
            status = MissingReason.UNIT_NOT_RESOLVED
        elif primary in {PERIOD_UNKNOWN, "DURATION_UNKNOWN", "ROLE_UNKNOWN"}:
            status = MissingReason.PERIOD_NOT_RESOLVED
        elif primary == ENTITY_UNKNOWN:
            status = MissingReason.ENTITY_NOT_RESOLVED
        else:
            status = MissingReason.VALUE_CONTEXT_UNRESOLVED
        exemplar = max(unresolved, key=lambda e: e.score)
        return QueriedFact(query.metric_code, query.concept, exemplar, str(status), primary, trace, tuple(reasons))

    rejected = [e for e in all_entries if e.status == "rejected"]
    rejected_blob = _reason_histogram(rejected)
    if rejected:
        if any(r == YTD_CANNOT_SATISFY_3M or "YTD" in r for r in rejected_blob):
            return QueriedFact(
                query.metric_code,
                query.concept,
                None,
                str(MissingReason.ONLY_CUMULATIVE_CANDIDATES_LOCATED),
                YTD_CANNOT_SATISFY_3M,
                trace,
                tuple(rejected_blob),
            )
        if any(r == GROUP_CANNOT_SATISFY_COMPANY or "GROUP" in r for r in rejected_blob):
            return QueriedFact(
                query.metric_code,
                query.concept,
                None,
                str(MissingReason.ONLY_GROUP_CANDIDATES_LOCATED),
                GROUP_CANNOT_SATISFY_COMPANY,
                trace,
                tuple(rejected_blob),
            )
        if any(r == COMPARATIVE_NOT_CURRENT for r in rejected_blob):
            return QueriedFact(
                query.metric_code,
                query.concept,
                None,
                str(MissingReason.ONLY_COMPARATIVE_CANDIDATES_LOCATED),
                COMPARATIVE_NOT_CURRENT,
                trace,
                tuple(rejected_blob),
            )
    status = (
        MissingReason.NOT_LOCATED_AFTER_CONFIGURED_RECOVERY if recovery_attempted else MissingReason.SEARCH_INCOMPLETE
    )
    return QueriedFact(
        query.metric_code,
        query.concept,
        None,
        str(status),
        "no_candidate_located" if not rejected else "all_candidates_rejected",
        trace,
        tuple(rejected_blob),
    )


def _concept_family(concept: str) -> tuple[str, ...]:
    from cse_financial_etl.accounting.ontology import TOP_LINE_FAMILY

    if concept == "TOP_LINE":
        return TOP_LINE_FAMILY
    return (concept,)


def _reason_histogram(entries: list[LedgerEntry]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in entries:
        for reason in entry.reasons:
            if reason in {"lower_than_arbiter_winner", "layout_assist"} or reason.startswith("legacy_status"):
                continue
            counts[reason] = counts.get(reason, 0) + 1
    return [r for r, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _trace(entries: list[LedgerEntry], recovery_attempted: bool) -> SearchTrace:
    return SearchTrace(
        candidates_seen=len(entries),
        pages=tuple(sorted({e.page for e in entries if e.page is not None})),
        columns=tuple(sorted({str(e.evidence.get("column_id")) for e in entries if e.evidence.get("column_id")})),
        rejected_reasons=tuple(_reason_histogram([e for e in entries if e.status == "rejected"])[:6]),
        unresolved_reasons=tuple(_reason_histogram([e for e in entries if e.status == "unresolved"])[:6]),
        recovery_attempted=recovery_attempted,
    )


def queried_values(facts: list[QueriedFact]) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {}
    for fact in facts:
        out[fact.metric_code] = fact.entry.normalized_value if fact.entry and fact.status == "EXTRACTED" else None
    return out
