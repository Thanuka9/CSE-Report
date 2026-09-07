"""PDF ingestion: native, OCR, and quality routing into CanonicalDocumentIR."""

from __future__ import annotations

from cse_financial_etl.ingestion.native_pdf import extract_native_document
from cse_financial_etl.ingestion.ocr_pdf import extract_ocr_document
from cse_financial_etl.ingestion.quality_router import route_document_ingestion

__all__ = [
    "extract_native_document",
    "extract_ocr_document",
    "route_document_ingestion",
]
