"""V2 document ingestion. Downstream modules consume CanonicalDocument only."""

from __future__ import annotations

from cse_financial_etl.v2.document.native_reader import read_native_pdf, sha256_file
from cse_financial_etl.v2.document.ocr_reader import read_ocr_pdf
from cse_financial_etl.v2.document.quality import DocumentQualityFeatures, measure_document_quality
from cse_financial_etl.v2.document.router import read_document, select_reader_route

__all__ = [
    "DocumentQualityFeatures",
    "measure_document_quality",
    "read_document",
    "read_native_pdf",
    "read_ocr_pdf",
    "select_reader_route",
    "sha256_file",
]
