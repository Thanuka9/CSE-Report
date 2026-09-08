"""Evidence arbitration — shared eligibility contract, then scoring, then abstention (§30).

* Every candidate is filtered through :func:`evaluate_eligibility` (the same contract
  the final validator re-runs on the chosen evidence).
* Hard failures (disproven for the target) are rejected with the concrete reason;
  unresolved dimensions stay ``unresolved`` so recovery can still act on them.
* Equal-score candidates with *conflicting* values abstain (UNRESOLVED). There is no
  origin-preference tiebreak. Equal-score candidates with the *same* value corroborate
  each other and the best-evidenced one is selected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cse_financial_etl.contracts.eligibility import (
    COMPARATIVE_NOT_CURRENT,
    DERIVED_LIABILITIES_FORBIDDEN,
    DIMENSION_MISMATCH,
    ENTITY_MISMATCH,
    GROUP_CANNOT_SATISFY_COMPANY,
    LABEL_EVIDENCE_WEAK,
    PERIOD_MISMATCH,
    YTD_CANNOT_SATISFY_3M,
    evaluate_eligibility,
)
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.resolution.factor_scores import score_factors

# Failures that disprove the candidate for this target (terminal for the query).
HARD_REJECT_REASONS = frozenset(
    {
        GROUP_CANNOT_SATISFY_COMPANY,
        ENTITY_MISMATCH,
        PERIOD_MISMATCH,
        YTD_CANNOT_SATISFY_3M,
        COMPARATIVE_NOT_CURRENT,
        DERIVED_LIABILITIES_FORBIDDEN,
        DIMENSION_MISMATCH,
        LABEL_EVIDENCE_WEAK,
    }
)
TIE_MARGIN = 0.1


@dataclass(frozen=True, slots=True)
class ArbitrationDecision:
    concept: str
    selected: LedgerEntry | None
    status: str  # SELECTED | UNRESOLVED | INELIGIBLE_ONLY
    reason: str
    reasons: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = field(default_factory=tuple)


def arbitrate_candidates(
    ledger: CandidateLedger,
    *,
    required_entity: str,
    target_duration: int = 3,
    target_period_end: str | None = None,
) -> list[ArbitrationDecision]:
    decisions: list[ArbitrationDecision] = []
    concepts = sorted({e.concept for e in ledger.entries})
    for concept in concepts:
        pool = [e for e in ledger.for_concept(concept) if e.status != "rejected"]
        eligible: list[LedgerEntry] = []
        ineligible_reasons: list[str] = []
        for entry in pool:
            result = evaluate_eligibility(
                entry,
                required_entity=required_entity,
                target_duration=target_duration,
                target_period_end=target_period_end,
            )
            if result.eligible:
                eligible.append(entry)
                continue
            ineligible_reasons.extend(result.reasons)
            hard = [r for r in result.reasons if r in HARD_REJECT_REASONS]
            if hard:
                ledger.reject(entry.entry_id, hard[0])
            else:
                entry.status = "unresolved"
                for reason in result.reasons:
                    if reason not in entry.reasons:
                        entry.reasons.append(reason)
        if not eligible:
            decisions.append(
                ArbitrationDecision(
                    concept,
                    None,
                    "INELIGIBLE_ONLY",
                    "no_eligible",
                    reasons=tuple(dict.fromkeys(ineligible_reasons)),
                )
            )
            continue

        def _score(entry: LedgerEntry) -> float:
            return score_factors(entry, required_entity=required_entity, target_duration=target_duration)

        ranked = sorted(eligible, key=_score, reverse=True)
        top_score = _score(ranked[0])
        tied = [e for e in ranked if top_score - _score(e) < TIE_MARGIN]
        if len(tied) > 1:
            values = {e.normalized_value for e in tied}
            if len(values) > 1:
                # Conflicting values with indistinguishable evidence → abstain.
                for entry in ranked:
                    entry.status = "unresolved"
                    if "AMBIGUOUS_EQUAL_SCORE" not in entry.reasons:
                        entry.reasons.append("AMBIGUOUS_EQUAL_SCORE")
                decisions.append(
                    ArbitrationDecision(
                        concept,
                        None,
                        "UNRESOLVED",
                        "indistinguishable_conflicting_values",
                        reasons=("AMBIGUOUS_EQUAL_SCORE",),
                        alternatives=tuple(e.entry_id for e in tied),
                    )
                )
                continue
            # Same value from several places: corroboration, not conflict.
            winner = ranked[0]
            winner.evidence["corroborated_by"] = [e.entry_id for e in tied[1:]]
        winner = ranked[0]
        winner.status = "accepted"
        for entry in ranked[1:]:
            entry.status = "alternative"
            entry.reasons.append("lower_than_arbiter_winner")
        decisions.append(
            ArbitrationDecision(
                concept,
                winner,
                "SELECTED",
                "eligible_rank",
                alternatives=tuple(e.entry_id for e in ranked[1:]),
            )
        )
    return decisions
