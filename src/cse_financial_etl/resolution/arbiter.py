"""Evidence arbitration — hard eligibility before scoring (§30)."""

from __future__ import annotations

from dataclasses import dataclass

from cse_financial_etl.accounting.concept_rules import (
    group_cannot_satisfy_company,
    requires_exact_3m,
)
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.resolution.factor_scores import score_factors


@dataclass(frozen=True, slots=True)
class ArbitrationDecision:
    concept: str
    selected: LedgerEntry | None
    status: str  # SELECTED | UNRESOLVED | INELIGIBLE_ONLY
    reason: str


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
        for entry in pool:
            if entry.normalized_value is None:
                # Absence / miss rows are not publishable selections.
                continue
            if group_cannot_satisfy_company(required_entity, entry.entity or ""):
                ledger.reject(entry.entry_id, "GROUP_CANNOT_SATISFY_COMPANY")
                continue
            if (
                requires_exact_3m(concept)
                and entry.duration_months not in {None, target_duration}
                and entry.duration_months
                and entry.duration_months != target_duration
            ):
                ledger.reject(entry.entry_id, "YTD_CANNOT_SATISFY_3M")
                continue
            if entry.comparison_role == "COMPARATIVE":
                ledger.reject(entry.entry_id, "COMPARATIVE_NOT_CURRENT")
                continue
            if target_period_end and entry.period_end and entry.period_end != target_period_end:
                ledger.reject(entry.entry_id, "PERIOD_MISMATCH")
                continue
            eligible.append(entry)
        if not eligible:
            decisions.append(ArbitrationDecision(concept, None, "INELIGIBLE_ONLY", "no_eligible"))
            continue
        ranked = sorted(
            eligible,
            key=lambda e: score_factors(e, required_entity=required_entity, target_duration=target_duration),
            reverse=True,
        )
        if len(ranked) > 1:
            top = score_factors(ranked[0], required_entity=required_entity, target_duration=target_duration)
            second = score_factors(ranked[1], required_entity=required_entity, target_duration=target_duration)
            if top - second < 0.1:
                # Prefer mature layout-assist evidence over abstention when scores collide.
                layout_pool = [
                    e
                    for e in ranked
                    if e.evidence.get("candidate_origin") == "layout_geometry"
                    and e.normalized_value is not None
                ]
                if layout_pool:
                    winner = max(
                        layout_pool,
                        key=lambda e: score_factors(
                            e, required_entity=required_entity, target_duration=target_duration
                        ),
                    )
                    winner.status = "accepted"
                    winner.reasons.append("layout_assist_tiebreak")
                    for entry in ranked:
                        if entry.entry_id != winner.entry_id:
                            entry.status = "alternative"
                            entry.reasons.append("lower_than_arbiter_winner")
                    decisions.append(
                        ArbitrationDecision(
                            concept, winner, "SELECTED", "layout_assist_tiebreak"
                        )
                    )
                    continue
                for entry in ranked:
                    entry.status = "unresolved"
                decisions.append(ArbitrationDecision(concept, None, "UNRESOLVED", "indistinguishable"))
                continue
        winner = ranked[0]
        winner.status = "accepted"
        for entry in ranked[1:]:
            entry.status = "alternative"
            entry.reasons.append("lower_than_arbiter_winner")
        decisions.append(ArbitrationDecision(concept, winner, "SELECTED", "eligible_rank"))
    return decisions
