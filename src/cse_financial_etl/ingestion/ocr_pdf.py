"""OCR ingestion for scanned / image-only / corrupted native text pages."""

from __future__ import annotations

from pathlib import Path

from cse_financial_etl.document.document_ir import CanonicalDocumentIR, from_legacy_document_ir
from cse_financial_etl.documents.document_ir import extract_document_ir


def extract_ocr_document(pdf_path: Path, *, ocr_dir: Path | None = None) -> CanonicalDocumentIR:
    """OCR path feeds the same CanonicalDocumentIR as native ingestion."""

    legacy = extract_document_ir(pdf_path, ocr_dir=ocr_dir, enable_ocr=True)
    return from_legacy_document_ir(legacy, source_method="ocr")
