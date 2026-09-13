from __future__ import annotations

from pathlib import Path

import pytest

from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.document.ocr_reader import read_ocr_pdf
from cse_financial_etl.v2.document.quality import measure_document_quality
from cse_financial_etl.v2.document.router import read_document, select_reader_route
from cse_financial_etl.v2.statements.detector import detect_statement_regions

SCANNED = Path(__file__).resolve().parents[2] / "fixtures" / "ocr" / "scanned_sample.pdf"


def test_scanned_sample_uses_ocr_canonical_document() -> None:
    if not SCANNED.is_file():
        pytest.skip("scanned_sample.pdf is not present")
    native = read_native_pdf(SCANNED, filing_version_id="ocr-scan")
    quality = measure_document_quality(native)
    if quality.native_token_count == 0:
        assert select_reader_route(quality) is ExtractionMode.OCR
        document = read_document(SCANNED, filing_version_id="ocr-scan")
    else:
        document = read_ocr_pdf(SCANNED, filing_version_id="ocr-scan")
    assert document.pages[0].extraction_mode is ExtractionMode.OCR
    regions = detect_statement_regions(document)
    assert regions
    assert document.source_sha256
    assert document.parser_manifest.get("parser_name") in {
        "v2.ocr.tesseract",
        "v2.ocr.canonical_fallback",
    }
