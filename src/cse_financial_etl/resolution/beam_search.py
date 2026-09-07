"""Bounded beam search over ambiguity components (§28, §35)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from cse_financial_etl.resolution.candidate_ledger import LedgerEntry
from cse_financial_etl.resolution.factor_scores import score_factors


@dataclass(frozen=True, slots=True)
class BeamSearchResult:
    winner: LedgerEntry | None
    status: str  # RESOLVED | ABSTAIN | SEARCH_BUDGET_EXHAUSTED
    alternatives: tuple[LedgerEntry, ...]
    detail: str


def beam_search_concept(
    candidates: list[LedgerEntry],
    *,
    required_entity: str,
    target_duration: int,
    beam_width: int = 5,
    max_iterations: int = 50,
    time_budget_ms: int = 200,
) -> BeamSearchResult:
    start = time.perf_counter()
    eligible = [
        c
        for c in candidates
        if not (
            c.entity == "GROUP"
            and required_entity in {"COMPANY", "BANK"}
        )
        and not (
            c.duration_months is not None
            and c.duration_months != target_duration
            and c.concept
            not in {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES", "NAVPS"}
        )
    ]
    if not eligible:
        return BeamSearchResult(None, "ABSTAIN", tuple(candidates), "no_eligible_candidates")
    ranked = sorted(
        eligible,
        key=lambda c: score_factors(c, required_entity=required_entity, target_duration=target_duration),
        reverse=True,
    )[:beam_width]
    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        if (time.perf_counter() - start) * 1000 > time_budget_ms:
            return BeamSearchResult(
                None,
                "SEARCH_BUDGET_EXHAUSTED",
                tuple(ranked),
                "time_budget",
            )
        if len(ranked) == 1:
            return BeamSearchResult(ranked[0], "RESOLVED", tuple(ranked), "unique")
        # Distinguishability: require clear margin.
        top = score_factors(ranked[0], required_entity=required_entity, target_duration=target_duration)
        second = score_factors(ranked[1], required_entity=required_entity, target_duration=target_duration)
        if top - second >= 0.15:
            return BeamSearchResult(ranked[0], "RESOLVED", tuple(ranked), "margin")
        return BeamSearchResult(None, "ABSTAIN", tuple(ranked), "indistinguishable")
    return BeamSearchResult(None, "SEARCH_BUDGET_EXHAUSTED", tuple(ranked), "iterations")
