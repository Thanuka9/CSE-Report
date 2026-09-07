"""Native PDF geometry ingestion via PyMuPDF (primary) with measured fallbacks."""

from __future__ import annotations

from pathlib import Path

from cse_financial_etl.document.document_ir import CanonicalDocumentIR, from_legacy_document_ir
from cse_financial_etl.documents.document_ir import extract_document_ir


def extract_native_document(pdf_path: Path) -> CanonicalDocumentIR:
    """Build CanonicalDocumentIR without accounting decisions."""

    legacy = extract_document_ir(pdf_path, enable_ocr=False)
    return from_legacy_document_ir(legacy, source_method="native")
