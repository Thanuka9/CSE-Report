from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
import pytest

from cse_financial_etl.v2 import PARSER_NAME_NATIVE
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.native_reader import read_native_pdf, sha256_file
from cse_financial_etl.v2.document.ocr_reader import _tesseract_engine, read_ocr_pdf
from cse_financial_etl.v2.document.quality import measure_document_quality
from cse_financial_etl.v2.document.router import read_document, select_reader_route
from cse_financial_etl.v2.exceptions import NativeParseError, OcrRouteNotEnabledError
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from tests.v2.helpers import geometric_document


def _write_native_pdf(path: Path) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "GROUP / 6 months / 30-Jun-26 / Rs '000")
    page.insert_text((72, 108), "Profit after tax          1,234")
    page.insert_text((72, 144), "Total equity              9,876")
    document.save(path)
    document.close()


def test_native_reader_is_deterministic(tmp_path: Path) -> None:
    pdf_path = tmp_path / "native.pdf"
    _write_native_pdf(pdf_path)
    first = read_native_pdf(pdf_path, filing_version_id="fv-test")
    second = read_native_pdf(pdf_path, filing_version_id="fv-test")
    assert first == second
    assert first.source_sha256 == sha256_file(pdf_path)
    assert first.parser_manifest["parser_name"] == PARSER_NAME_NATIVE
    assert first.pages[0].extraction_mode == ExtractionMode.NATIVE
    texts = [line.text for page in first.pages for line in page.lines]
    assert any("GROUP" in text for text in texts)
    assert any("1,234" in text for text in texts)
    token = first.pages[0].lines[0].tokens[0]
    assert token.bbox[2] >= token.bbox[0]
    assert token.page_number == 1
    assert token.source_parser == PARSER_NAME_NATIVE
    quality = measure_document_quality(first)
    assert quality.native_token_count >= 8
    assert quality.numeric_token_count >= 2


def test_native_reader_does_not_map_financial_concepts(tmp_path: Path) -> None:
    pdf_path = tmp_path / "native.pdf"
    _write_native_pdf(pdf_path)
    document = read_native_pdf(pdf_path, filing_version_id="fv-test")
    dumped = document.model_dump()
    assert "metric_code" not in dumped
    assert "entity_scope" not in dumped


def test_missing_pdf_is_typed_error(tmp_path: Path) -> None:
    with pytest.raises(NativeParseError):
        read_native_pdf(tmp_path / "missing.pdf", filing_version_id="fv-test")


def test_ocr_path_uses_the_same_canonical_document(tmp_path: Path) -> None:
    pdf_path = tmp_path / "native.pdf"
    _write_native_pdf(pdf_path)
    native = read_native_pdf(pdf_path, filing_version_id="fv-test")
    if _tesseract_engine() is None:
        with pytest.raises(OcrRouteNotEnabledError, match="OCR_REQUIRED_NOT_AVAILABLE"):
            read_ocr_pdf(pdf_path, filing_version_id="fv-test")
        return
    ocr = read_ocr_pdf(pdf_path, filing_version_id="fv-test")
    assert ocr.pages[0].extraction_mode == ExtractionMode.OCR
    assert native.source_sha256 == ocr.source_sha256
    assert ocr.parser_manifest.get("parser_name") == "v2.ocr.tesseract"
    assert any(line.tokens for line in ocr.pages[0].lines)
    assert select_reader_route() == ExtractionMode.NATIVE
    assert "page_routing" not in native.parser_manifest


def test_empty_native_text_routes_to_ocr(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scan.pdf"
    document = fitz.open()
    document.new_page(width=612, height=792)
    document.save(pdf_path)
    document.close()
    native = read_native_pdf(pdf_path, filing_version_id="fv-test")
    quality = measure_document_quality(native)
    assert quality.native_token_count == 0
    assert select_reader_route(quality) == ExtractionMode.OCR
    if _tesseract_engine() is None:
        with pytest.raises(OcrRouteNotEnabledError, match="OCR_REQUIRED_NOT_AVAILABLE"):
            read_document(pdf_path, filing_version_id="fv-test")
        return
    routed = read_document(pdf_path, filing_version_id="fv-test")
    assert routed.pages[0].extraction_mode == ExtractionMode.OCR


def test_ocr_canonical_document_uses_the_same_detector() -> None:
    native = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    ocr = native.model_copy(
        update={
            "pages": tuple(
                page.model_copy(update={"extraction_mode": ExtractionMode.OCR})
                for page in native.pages
            )
        }
    )
    native_regions = detect_statement_regions(native)
    ocr_regions = detect_statement_regions(ocr)
    assert native_regions
    assert [region.statement_type for region in native_regions] == [
        region.statement_type for region in ocr_regions
    ]
