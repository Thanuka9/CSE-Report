from __future__ import annotations

import os
from pathlib import Path

import pymupdf as fitz
import pytest

from cse_financial_etl.v2 import PARSER_NAME_OCR
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.document.ocr_reader import _tesseract_engine, read_ocr_pdf
from cse_financial_etl.v2.document.quality import measure_document_quality
from cse_financial_etl.v2.document.router import read_document, select_reader_route
from cse_financial_etl.v2.exceptions import OcrRouteNotEnabledError
from cse_financial_etl.v2.statements.detector import detect_statement_regions

SCANNED = Path(__file__).resolve().parents[2] / "fixtures" / "ocr" / "scanned_sample.pdf"


def _write_image_only_income_pdf(path: Path) -> None:
    text_doc = fitz.open()
    text_page = text_doc.new_page(width=612, height=792)
    text_page.insert_text((72, 72), "STATEMENT OF PROFIT OR LOSS", fontsize=18)
    text_page.insert_text((72, 108), "For the three months ended 30 June 2026", fontsize=14)
    text_page.insert_text((72, 144), "Company", fontsize=14)
    text_page.insert_text((72, 180), "Rs '000", fontsize=14)
    text_page.insert_text((72, 216), "Profit for the period          1,234", fontsize=14)
    pixmap = text_page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
    text_doc.close()
    image_doc = fitz.open()
    image_page = image_doc.new_page(width=612, height=792)
    image_page.insert_image(image_page.rect, pixmap=pixmap)
    image_doc.save(path)
    image_doc.close()


def test_image_only_pdf_has_zero_native_tokens(tmp_path: Path) -> None:
    pdf_path = tmp_path / "image-only.pdf"
    _write_image_only_income_pdf(pdf_path)
    native = read_native_pdf(pdf_path, filing_version_id="ocr-image")
    quality = measure_document_quality(native)
    assert quality.native_token_count == 0
    assert select_reader_route(quality) is ExtractionMode.OCR


def test_ocr_required_fails_closed_without_engine(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "image-only.pdf"
    _write_image_only_income_pdf(pdf_path)
    monkeypatch.setattr(
        "cse_financial_etl.v2.document.ocr_reader._tesseract_engine", lambda: None
    )
    with pytest.raises(OcrRouteNotEnabledError, match="OCR_REQUIRED_NOT_AVAILABLE"):
        read_ocr_pdf(pdf_path, filing_version_id="ocr-image")
    with pytest.raises(OcrRouteNotEnabledError, match="OCR_REQUIRED_NOT_AVAILABLE"):
        read_document(pdf_path, filing_version_id="ocr-image")


def test_real_ocr_emits_tokens_bboxes_and_lineage(tmp_path: Path) -> None:
    if _tesseract_engine() is None:
        if os.environ.get("CSE_REQUIRE_REAL_OCR") == "1":
            pytest.fail("CSE_REQUIRE_REAL_OCR=1 but tesseract is not available")
        pytest.skip("tesseract is not installed")
    pdf_path = tmp_path / "image-only.pdf"
    _write_image_only_income_pdf(pdf_path)
    native = read_native_pdf(pdf_path, filing_version_id="ocr-image")
    assert measure_document_quality(native).native_token_count == 0
    document = read_document(pdf_path, filing_version_id="ocr-image")
    tokens = [token for page in document.pages for line in page.lines for token in line.tokens]
    assert document.pages[0].extraction_mode is ExtractionMode.OCR
    assert document.parser_manifest.get("parser_name") == PARSER_NAME_OCR
    assert len(tokens) > 0
    assert all(token.bbox[2] >= token.bbox[0] for token in tokens)
    assert all(token.source_parser == PARSER_NAME_OCR for token in tokens)
    assert detect_statement_regions(document)


def test_scanned_sample_uses_ocr_canonical_document() -> None:
    if not SCANNED.is_file():
        pytest.skip("scanned_sample.pdf is not present")
    native = read_native_pdf(SCANNED, filing_version_id="ocr-scan")
    quality = measure_document_quality(native)
    if quality.native_token_count != 0:
        pytest.skip("scanned_sample.pdf still has a native text layer")
    assert select_reader_route(quality) is ExtractionMode.OCR
    if _tesseract_engine() is None:
        with pytest.raises(OcrRouteNotEnabledError, match="OCR_REQUIRED_NOT_AVAILABLE"):
            read_document(SCANNED, filing_version_id="ocr-scan")
        return
    document = read_document(SCANNED, filing_version_id="ocr-scan")
    assert document.pages[0].extraction_mode is ExtractionMode.OCR
    assert document.parser_manifest.get("parser_name") == PARSER_NAME_OCR
    assert document.source_sha256
    assert detect_statement_regions(document)
