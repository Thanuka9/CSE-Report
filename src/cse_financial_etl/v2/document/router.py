"""Document reader routing. OCR is used only when native text is absent."""

from __future__ import annotations

from pathlib import Path

from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.document.ocr_reader import read_ocr_pdf
from cse_financial_etl.v2.document.quality import DocumentQualityFeatures, measure_document_quality


def select_reader_route(features: DocumentQualityFeatures | None = None) -> ExtractionMode:
    """Scan-like empty native text routes to OCR. Token-count competition is forbidden."""

    if features is not None and features.native_token_count == 0:
        return ExtractionMode.OCR
    return ExtractionMode.NATIVE


def read_document(
    pdf_path: Path, *, filing_version_id: str, force_ocr: bool = False
) -> CanonicalDocument:
    if force_ocr:
        return read_ocr_pdf(pdf_path, filing_version_id=filing_version_id)
    native = read_native_pdf(pdf_path, filing_version_id=filing_version_id)
    route = select_reader_route(measure_document_quality(native))
    if route is ExtractionMode.OCR:
        return read_ocr_pdf(pdf_path, filing_version_id=filing_version_id)
    return native


def read_document_with_quality(
    pdf_path: Path, *, filing_version_id: str
) -> tuple[CanonicalDocument, DocumentQualityFeatures]:
    document = read_document(pdf_path, filing_version_id=filing_version_id)
    return document, measure_document_quality(document)
