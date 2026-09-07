"""Query accepted ledger / canonical statements for target metrics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cse_financial_etl.facts.target_metrics import TargetQuery, default_queries
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry


@dataclass(frozen=True, slots=True)
class QueriedFact:
    metric_code: str
    concept: str
    entry: LedgerEntry | None
    status: str
    issue: str | None = None


def query_target_facts(
    ledger: CandidateLedger,
    *,
    entity: str,
    period_end,
) -> list[QueriedFact]:
    results: list[QueriedFact] = []
    for query in default_queries(entity=entity, period_end=period_end):
        results.append(_query_one(ledger, query))
    return results


def _query_one(ledger: CandidateLedger, query: TargetQuery) -> QueriedFact:
    accepted = [
        e
        for e in ledger.for_concept(query.concept)
        if e.status == "accepted"
        and (e.entity is None or e.entity == query.entity or query.entity in {e.entity})
    ]
    if query.duration_months is not None:
        exact = [e for e in accepted if e.duration_months in {None, query.duration_months}]
        # Prefer exact duration matches.
        preferred = [e for e in exact if e.duration_months == query.duration_months] or exact
    else:
        preferred = accepted
    if not preferred:
        unresolved = [e for e in ledger.for_concept(query.concept) if e.status == "unresolved"]
        if unresolved:
            return QueriedFact(query.metric_code, query.concept, unresolved[0], "VALUE_CONTEXT_UNRESOLVED", "unresolved_after_arbiter")
        rejected = ledger.for_concept(query.concept)
        if any("YTD" in " ".join(e.reasons) or "DURATION" in " ".join(e.reasons) for e in rejected):
            return QueriedFact(query.metric_code, query.concept, None, "CUMULATIVE_ONLY", "only_cumulative_candidates")
        if any("GROUP" in " ".join(e.reasons) for e in rejected):
            return QueriedFact(query.metric_code, query.concept, None, "VALUE_CONTEXT_UNRESOLVED", "ONLY_GROUP_CANDIDATES_LOCATED")
        return QueriedFact(query.metric_code, query.concept, None, "NOT_FOUND_BY_PARSER", "not_located")
    best = max(preferred, key=lambda e: e.score)
    return QueriedFact(query.metric_code, query.concept, best, "EXTRACTED", None)


def queried_values(facts: list[QueriedFact]) -> dict[str, Decimal | None]:
    out: dict[str, Decimal | None] = {}
    for fact in facts:
        out[fact.metric_code] = fact.entry.normalized_value if fact.entry else None
    return out
