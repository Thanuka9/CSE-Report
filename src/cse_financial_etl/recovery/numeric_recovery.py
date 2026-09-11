"""Numeric corruption recovery — reparse only evidence owned by the same entry (§33.4)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.compiler.structure_normalizer import parse_numeric
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry


def _owned_numeric_text(entry: LedgerEntry) -> str | None:
    evidence = entry.evidence if isinstance(entry.evidence, dict) else {}
    for key in ("raw_numeric_text", "source_numeric_text", "numeric_token_text"):
        value = evidence.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def recover_numeric(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Reparse a candidate's own numeric token; never borrow another row's value.

    Filing-wide ``raw_numeric_texts`` are intentionally ignored.  Without source-owned
    numeric evidence there is no safe way to decide which number belongs to this row.
    Missing scale also stays missing instead of silently defaulting to whole units.
    """

    reparsed = 0
    for entry in ledger.for_concept(ticket.concept):
        if entry.raw_value is not None:
            continue
        raw_text = _owned_numeric_text(entry)
        if raw_text is None:
            continue
        value = parse_numeric(raw_text)
        if value is None:
            continue
        entry.raw_value = value
        entry.normalized_value = (
            value * entry.scale_factor if entry.scale_factor is not None else None
        )
        entry.status = "unresolved"
        if "numeric_recovery_reparse_owned_token" not in entry.reasons:
            entry.reasons.append("numeric_recovery_reparse_owned_token")
        reparsed += 1

    if reparsed:
        return {"status": "RECOVERED", "reparsed": reparsed}
    return {"status": "NO_CHANGE", "reason": "no_entry_owned_numeric_evidence"}
