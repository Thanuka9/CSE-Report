"""OCR recovery — rerun the same compiler on OCR geometry (§33)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cse_financial_etl.ingestion.ocr_pdf import extract_ocr_document
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger
from cse_financial_etl.tunnels.common_financial_engine import apply_financial_engine


def recover_ocr(
    ticket: FailureTicket,
    ledger: CandidateLedger,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Re-read the source through OCR and add fresh candidates for the failed concept.

    This is a materially different read, not a relabel of candidates already on the
    ledger. It preserves the same KnownContext, so OCR can never relax entity/period/
    duration requirements.
    """

    pdf_path = context.get("pdf_path")
    known = context.get("known")
    if not pdf_path or known is None:
        return {"status": "SKIPPED", "reason": "missing_pdf_or_known_context"}
    path = Path(str(pdf_path))
    if not path.exists():
        return {"status": "SKIPPED", "reason": "pdf_missing"}

    cache = context.setdefault("_ocr_recovery_cache", {})
    cache_key = str(path.resolve())
    if cache_key not in cache:
        try:
            document = extract_ocr_document(path, ocr_dir=context.get("ocr_dir"))
            _statements, ocr_ledger, _graph = apply_financial_engine(document, known, tunnel="OCR")
            cache[cache_key] = ocr_ledger
        except Exception as exc:
            return {"status": "SKIPPED", "reason": "ocr_failed", "detail": str(exc)}

    ocr_ledger = cache[cache_key]
    existing = {entry.entry_id for entry in ledger.entries}
    added = 0
    for entry in ocr_ledger.for_concept(ticket.concept):
        if entry.entry_id in existing:
            continue
        entry.status = "unresolved" if entry.status != "rejected" else entry.status
        entry.reasons.append("ocr_recovery_candidate")
        ledger.add(entry)
        existing.add(entry.entry_id)
        added += 1
    return {
        "status": "RECOVERED" if added else "NO_CHANGE",
        "added_candidates": added,
        "reason": None if added else "ocr_no_matching_candidates",
    }