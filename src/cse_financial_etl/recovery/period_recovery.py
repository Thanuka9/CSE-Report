"""Period/duration recovery — never relax exact 3M into cumulative YTD (§33.6)."""

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
    target_duration = int(context.get("target_duration") or 3)
    exact = [
        e
        for e in ledger.for_concept(ticket.concept)
        if e.duration_months == target_duration and e.status != "rejected"
    ]
    if exact:
        best = max(exact, key=lambda e: e.score)
        best.status = "unresolved"
        best.reasons.append("period_recovery_exact_duration")
        for entry in ledger.for_concept(ticket.concept):
            if entry.duration_months and entry.duration_months != target_duration:
                entry.status = "rejected"
                entry.reasons.append("period_recovery_rejects_ytd_substitution")
        return {"status": "RECOVERED", "entry_id": best.entry_id}
    return {"status": "NO_CHANGE", "reason": "no_exact_duration_candidate"}
