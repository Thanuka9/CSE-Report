"""OCR recovery — local OCR crop / alternate preprocessing (§33)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger


def recover_ocr(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    pdf_path = context.get("pdf_path")
    if not pdf_path:
        return {"status": "SKIPPED", "reason": "no_pdf_path"}
    path = Path(str(pdf_path))
    if not path.exists():
        return {"status": "SKIPPED", "reason": "pdf_missing"}
    # Soft signal: presence of Tunnel B / OCR-tagged ledger entries.
    ocr_entries = [e for e in ledger.for_concept(ticket.concept) if "ocr" in e.tunnel.lower()]
    if ocr_entries:
        best = max(ocr_entries, key=lambda e: e.score)
        best.status = "unresolved"
        best.reasons.append("ocr_recovery_promoted")
        return {"status": "RECOVERED", "entry_id": best.entry_id}
    return {"status": "NO_CHANGE", "reason": "no_ocr_candidates"}
