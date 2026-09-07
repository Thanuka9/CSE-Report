"""Structural recovery — alternate grouping / table boundaries (§33.1)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_structural(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    # Prefer Tunnel B candidates already on the ledger for the same concept.
    alts = [
        e
        for e in ledger.for_concept(ticket.concept)
        if e.tunnel == "B" and e.status != "rejected"
    ]
    if not alts:
        return {"status": "NO_CHANGE", "reason": "no_tunnel_b_candidate"}
    best = max(alts, key=lambda e: e.score)
    best.status = "unresolved"
    best.reasons.append("structural_recovery_promoted_tunnel_b")
    return {"status": "RECOVERED", "entry_id": best.entry_id, "tunnel": "B"}
