"""Bounded candidate ranking; truncation cannot turn ambiguity into certainty."""
from __future__ import annotations

from dataclasses import dataclass

from cse_financial_etl.contracts.eligibility import evaluate_eligibility
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry
from cse_financial_etl.resolution.factor_scores import score_factors
from cse_financial_etl.resolution.resource_budget import ResourceBudget


@dataclass(frozen=True, slots=True)
class BeamSearchResult:
    winner: LedgerEntry | None
    status: str
    alternatives: tuple[LedgerEntry, ...]
    detail: str

def beam_search_concept(
    candidates: list[LedgerEntry], *, required_entity: str, target_duration: int,
    beam_width: int = 5, max_iterations: int = 50, time_budget_ms: int = 200,
    target_period_end: str | None = None, budget: ResourceBudget | None = None,
) -> BeamSearchResult:
    active = budget or ResourceBudget(beam_width=beam_width, max_iterations=max_iterations,
                                    max_elapsed_seconds=time_budget_ms / 1000)
    width = max(1, active.beam_width)
    ranked: list[tuple[float, LedgerEntry]] = []
    for candidate in candidates:
        if not active.consume_iteration():
            return BeamSearchResult(None, "SEARCH_BUDGET_EXHAUSTED", tuple(e for _, e in ranked[:width]), active.stop_reason or "budget")
        if not evaluate_eligibility(candidate, required_entity=required_entity,
                target_duration=target_duration, target_period_end=target_period_end).eligible:
            continue
        score = score_factors(candidate, required_entity=required_entity, target_duration=target_duration)
        ranked.append((score, candidate))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].entry_id))
        # Keep a runner-up even when beam_width=1: pruning is not independent evidence.
        ranked = ranked[:max(2, width)]
    alternatives = tuple(e for _, e in ranked[:width])
    if not ranked:
        return BeamSearchResult(None, "ABSTAIN", (), "no_eligible_candidates")
    if len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= .15:
        return BeamSearchResult(ranked[0][1], "RESOLVED", alternatives, "unique" if len(ranked)==1 else "margin")
    return BeamSearchResult(None, "ABSTAIN", alternatives, "indistinguishable")
