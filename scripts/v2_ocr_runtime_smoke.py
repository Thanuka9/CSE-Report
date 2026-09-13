"""Prove the production OCR runtime: image-only PDF → Tesseract tokens + bboxes.

Exit 0 only when native tokens are 0, OCR tokens exist, parser_name is
v2.ocr.tesseract, and every token has bbox evidence. Missing Tesseract is a
hard failure so a production image cannot silently skip OCR.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pymupdf as fitz

from cse_financial_etl.v2 import PARSER_NAME_OCR
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.document.quality import measure_document_quality
from cse_financial_etl.v2.document.router import read_document, select_reader_route


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


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "image-only.pdf"
        _write_image_only_income_pdf(pdf_path)
        native = read_native_pdf(pdf_path, filing_version_id="ocr-smoke")
        quality = measure_document_quality(native)
        if quality.native_token_count != 0:
            print("FAIL: image-only fixture still has native tokens", file=sys.stderr)
            return 1
        if select_reader_route(quality) is not ExtractionMode.OCR:
            print("FAIL: router did not select OCR", file=sys.stderr)
            return 1
        document = read_document(pdf_path, filing_version_id="ocr-smoke")
        tokens = [token for page in document.pages for line in page.lines for token in line.tokens]
        parser_name = document.parser_manifest.get("parser_name")
        if document.pages[0].extraction_mode is not ExtractionMode.OCR:
            print("FAIL: extraction_mode is not OCR", file=sys.stderr)
            return 1
        if parser_name != PARSER_NAME_OCR:
            print(f"FAIL: parser_name={parser_name!r}", file=sys.stderr)
            return 1
        if not tokens:
            print("FAIL: OCR produced zero tokens", file=sys.stderr)
            return 1
        if any(token.bbox[2] < token.bbox[0] or token.bbox[3] < token.bbox[1] for token in tokens):
            print("FAIL: OCR bbox evidence missing or inverted", file=sys.stderr)
            return 1
        print(
            f"PASS native_tokens=0 ocr_tokens={len(tokens)} parser_name={parser_name}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
