"""Numeric corruption recovery (§33.4)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.compiler.structure_normalizer import parse_numeric
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_numeric(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    raw_texts = context.get("raw_numeric_texts") or []
    for text in raw_texts:
        value = parse_numeric(text)
        if value is None:
            continue
        for entry in ledger.for_concept(ticket.concept):
            if entry.raw_value is None:
                entry.raw_value = value
                entry.normalized_value = value * (entry.scale_factor or 1)
                entry.status = "unresolved"
                entry.reasons.append("numeric_recovery_reparse")
                return {"status": "RECOVERED", "raw": text, "value": str(value)}
    return {"status": "NO_CHANGE", "reason": "no_reparses"}
