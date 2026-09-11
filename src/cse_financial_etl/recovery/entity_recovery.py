"""Entity recovery — preserve explicit target scope; never invent Company (§33.5)."""

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
    raw_required = context.get("required_entity")
    if raw_required is None or not str(raw_required).strip():
        return {"status": "SKIPPED", "reason": "missing_required_entity"}
    required = str(raw_required).strip().upper()
    if required not in {"COMPANY", "BANK", "GROUP"}:
        return {"status": "SKIPPED", "reason": "invalid_required_entity", "value": required}

    companyish = [
        e
        for e in ledger.for_concept(ticket.concept)
        if (e.entity or "").upper() == required and e.status != "rejected"
    ]
    if companyish:
        best = max(companyish, key=lambda e: e.score)
        best.status = "unresolved"
        if "entity_recovery_preferred_required_scope" not in best.reasons:
            best.reasons.append("entity_recovery_preferred_required_scope")
        for entry in ledger.for_concept(ticket.concept):
            if entry.entity == "GROUP" and required in {"COMPANY", "BANK"}:
                entry.status = "rejected"
                if "entity_recovery_keeps_group_ineligible" not in entry.reasons:
                    entry.reasons.append("entity_recovery_keeps_group_ineligible")
        return {"status": "RECOVERED", "entry_id": best.entry_id}
    return {"status": "NO_CHANGE", "reason": "no_required_entity_candidate"}
