"""Unit recovery — search unit evidence at cell→report scopes (§33.3)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.compiler.structure_normalizer import normalize_unit_declaration
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_unit(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    declarations = context.get("unit_texts") or []
    resolved = None
    for text in declarations:
        currency, scale = normalize_unit_declaration(text)
        if currency and scale is not None:
            resolved = (currency, int(scale))
            break
    if resolved is None:
        return {"status": "NO_CHANGE", "reason": "no_unit_evidence"}
    resolved_currency, resolved_scale = resolved
    changed = 0
    for entry in ledger.for_concept(ticket.concept):
        if entry.unit is None or entry.scale_factor is None:
            entry.unit = resolved_currency
            entry.scale_factor = resolved_scale
            if entry.raw_value is not None and entry.normalized_value is None:
                entry.normalized_value = entry.raw_value * resolved_scale
            entry.reasons.append("unit_recovery_applied")
            entry.status = "unresolved" if entry.status == "rejected" else entry.status
            changed += 1
    return {"status": "RECOVERED" if changed else "NO_CHANGE", "unit": resolved_currency, "scale": resolved_scale}
