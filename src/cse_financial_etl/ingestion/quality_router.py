"""Route filings to native vs OCR reconstruction based on measured fidelity."""

from __future__ import annotations

from pathlib import Path

from cse_financial_etl.document.document_ir import CanonicalDocumentIR
from cse_financial_etl.ingestion.native_cache import cached_native_document
from cse_financial_etl.ingestion.ocr_pdf import extract_ocr_document


def route_document_ingestion(
    pdf_path: Path,
    *,
    ocr_enabled: bool = True,
    ocr_dir: Path | None = None,
) -> CanonicalDocumentIR:
    """Prefer native geometry; escalate to OCR when quality.requires_ocr."""

    native = cached_native_document(pdf_path)
    if not native.quality.requires_ocr or not ocr_enabled:
        return native
    ocr = extract_ocr_document(pdf_path, ocr_dir=ocr_dir)
    if ocr.quality.token_count >= native.quality.token_count:
        return ocr
    return native
