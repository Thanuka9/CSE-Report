"""Period/duration recovery — never invent a target duration or relax 3M into YTD (§33.6)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_period(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    raw_duration = context.get("target_duration")
    if raw_duration is None or str(raw_duration).strip() == "":
        return {"status": "SKIPPED", "reason": "missing_target_duration"}
    try:
        target_duration = int(raw_duration)
    except (TypeError, ValueError):
        return {"status": "SKIPPED", "reason": "invalid_target_duration"}
    if target_duration <= 0:
        return {"status": "SKIPPED", "reason": "invalid_target_duration"}

    exact = [
        e
        for e in ledger.for_concept(ticket.concept)
        if e.duration_months == target_duration and e.status != "rejected"
    ]
    if exact:
        best = max(exact, key=lambda e: e.score)
        best.status = "unresolved"
        if "period_recovery_exact_duration" not in best.reasons:
            best.reasons.append("period_recovery_exact_duration")
        for entry in ledger.for_concept(ticket.concept):
            if entry.duration_months and entry.duration_months != target_duration:
                entry.status = "rejected"
                if "period_recovery_rejects_ytd_substitution" not in entry.reasons:
                    entry.reasons.append("period_recovery_rejects_ytd_substitution")
        return {"status": "RECOVERED", "entry_id": best.entry_id}
    return {"status": "NO_CHANGE", "reason": "no_exact_duration_candidate"}
