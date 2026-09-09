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


def _concept_budget(parent: ResourceBudget) -> ResourceBudget:
    """Give each concept a fair bounded scan while preserving the global wall clock.

    ``beam_search_concept`` consumes one iteration per candidate. Sharing the same
    iteration counter across alphabetically ordered concepts allowed early concepts to
    consume the entire budget and forced otherwise well-evidenced later concepts to
    ``SEARCH_BUDGET_EXHAUSTED``. The iteration cap is therefore a per-concept cap;
    the parent elapsed-time and hypothesis caps remain global bounds.
    """

    remaining = max(0.001, parent.max_elapsed_seconds - parent.elapsed())
    return ResourceBudget(
        max_hypotheses=parent.max_hypotheses,
        max_graph_nodes=parent.max_graph_nodes,
        beam_width=parent.beam_width,
        max_iterations=parent.max_iterations,
        max_elapsed_seconds=remaining,
        max_ocr_threads=parent.max_ocr_threads,
    )


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
    concepts = sorted(
        {e.concept for e in ledger.entries if e.status in {"unresolved", "alternative", "accepted"}}
    )
    total_candidates = sum(
        1
        for entry in ledger.entries
        if entry.status in {"unresolved", "alternative", "accepted"}
    )
    by_concept: dict[str, BeamSearchResult] = {}
    per_concept_budget: dict[str, dict[str, Any]] = {}
    total_iterations = 0

    global_hypothesis_exhausted = total_candidates > budget.max_hypotheses
    if global_hypothesis_exhausted:
        budget.stop_reason = "HYPOTHESIS_BUDGET_EXHAUSTED"

    for concept in concepts:
        candidates = [e for e in ledger.for_concept(concept) if e.status != "rejected"]
        if len(candidates) <= 1 and candidates and candidates[0].status == "accepted":
            by_concept[concept] = BeamSearchResult(
                candidates[0], "RESOLVED", tuple(candidates), "already_accepted"
            )
            continue

        if global_hypothesis_exhausted or budget.exhausted():
            detail = budget.stop_reason or "budget"
            result = BeamSearchResult(None, "SEARCH_BUDGET_EXHAUSTED", tuple(), detail)
        else:
            local_budget = _concept_budget(budget)
            result = beam_search_concept(
                candidates,
                required_entity=required_entity,
                target_duration=target_duration,
                target_period_end=target_period_end,
                budget=local_budget,
            )
            total_iterations += local_budget.iterations_used
            per_concept_budget[concept] = local_budget.as_dict()
            if local_budget.stop_reason == "ELAPSED_BUDGET_EXHAUSTED":
                budget.stop_reason = local_budget.stop_reason

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

    resource_report = budget.as_dict()
    resource_report.update(
        {
            "max_iterations_scope": "PER_CONCEPT",
            "total_iterations_used": total_iterations,
            "candidate_hypotheses": total_candidates,
            "per_concept": per_concept_budget,
        }
    )
    return ResolverCResult(
        by_concept=by_concept,
        report={
            "resource_budget": resource_report,
            "concepts": {
                concept: {
                    "status": result.status,
                    "detail": result.detail,
                    "winner": result.winner.entry_id if result.winner else None,
                }
                for concept, result in by_concept.items()
            },
        },
    )
