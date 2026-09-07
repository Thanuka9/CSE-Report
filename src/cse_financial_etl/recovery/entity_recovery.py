"""Entity recovery — rebuild multi-row entity headers; never relax Company→Group (§33.5)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_entity(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    required = str(context.get("required_entity") or "COMPANY").upper()
    # Never promote Group to satisfy Company/Bank.
    companyish = [
        e
        for e in ledger.for_concept(ticket.concept)
        if (e.entity or "").upper() == required and e.status != "rejected"
    ]
    if companyish:
        best = max(companyish, key=lambda e: e.score)
        best.status = "unresolved"
        best.reasons.append("entity_recovery_preferred_required_scope")
        # Ensure Group alternatives stay rejected for required Company/Bank.
        for entry in ledger.for_concept(ticket.concept):
            if entry.entity == "GROUP" and required in {"COMPANY", "BANK"}:
                entry.status = "rejected"
                entry.reasons.append("entity_recovery_keeps_group_ineligible")
        return {"status": "RECOVERED", "entry_id": best.entry_id}
    return {"status": "NO_CHANGE", "reason": "no_required_entity_candidate"}
