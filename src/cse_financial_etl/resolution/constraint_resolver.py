"""Resolver C — bounded constraint resolution over A/B evidence (§28)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cse_financial_etl.resolution.beam_search import BeamSearchResult, beam_search_concept
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger
from cse_financial_etl.resolution.resource_budget import ResourceBudget


@dataclass
class ResolverCResult:
    by_concept: dict[str, BeamSearchResult]
    report: dict[str, Any]


def resolve_ambiguities(
    ledger: CandidateLedger,
    *,
    required_entity: str,
    target_duration: int = 3,
    target_period_end: str | None = None,
    budget: ResourceBudget | None = None,
) -> ResolverCResult:
    """C is not an independent witness; it resolves compatible ambiguities or abstains."""

    budget = budget or ResourceBudget()
    concepts = sorted({e.concept for e in ledger.entries if e.status in {"unresolved", "alternative", "accepted"}})
    by_concept: dict[str, BeamSearchResult] = {}
    for concept in concepts:
        candidates = [e for e in ledger.for_concept(concept) if e.status != "rejected"]
        if len(candidates) <= 1 and candidates and candidates[0].status == "accepted":
            by_concept[concept] = BeamSearchResult(candidates[0], "RESOLVED", tuple(candidates), "already_accepted")
            continue
        result = beam_search_concept(
            candidates,
            required_entity=required_entity,
            target_duration=target_duration,
            target_period_end=target_period_end,
            budget=budget,
        )
        by_concept[concept] = result
        if result.status == "RESOLVED" and result.winner is not None:
            result.winner.status = "accepted"
            for alt in candidates:
                if alt.entry_id != result.winner.entry_id and alt.status != "rejected":
                    alt.status = "alternative"
                    alt.reasons.append("dominated_by_resolver_c")
        elif result.status in {"ABSTAIN", "SEARCH_BUDGET_EXHAUSTED"}:
            for alt in candidates:
                if alt.status == "accepted" or result.status == "SEARCH_BUDGET_EXHAUSTED":
                    alt.status = "unresolved"
                    alt.reasons.append(result.status)
    return ResolverCResult(
        by_concept=by_concept,
        report={
            "resource_budget": budget.as_dict(),
            "concepts": {
                concept: {
                    "status": result.status,
                    "detail": result.detail,
                    "winner": result.winner.entry_id if result.winner else None,
                }
                for concept, result in by_concept.items()
            }
        },
    )
