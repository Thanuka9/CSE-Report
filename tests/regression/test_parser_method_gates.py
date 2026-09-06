from pathlib import Path

import pytest

from cse_financial_etl.documents.document_ir import extract_document_ir


def _pdfs(folder: str) -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / folder
    if not root.exists():
        return []
    return sorted(root.glob("*.pdf"))


def test_ocr_fixture_extracts_or_marks_ocr_path() -> None:
    """OCR gate: scanned/image PDFs must route through OCR or record OCR requirement."""

    pdfs = _pdfs("ocr")
    if not pdfs:
        pytest.skip("OCR universe gate: add scanned CSE PDFs under tests/fixtures/ocr/")
    for pdf_path in pdfs:
        document = extract_document_ir(pdf_path, ocr_dir=pdf_path.parent / "ocr-cache")
        method = (document.quality.extraction_method or "").upper()
        assert document.pages, "OCR fixture produced no pages"
        assert (
            "OCR" in method
            or document.quality.requires_ocr
            or sum(len(line.tokens) for page in document.pages for line in page.lines) == 0
        )


def test_fallback_fixture_extracts_with_layout_tokens() -> None:
    """Fallback gate: weak-layout fixtures must still yield readable tokens."""

    pdfs = _pdfs("fallback")
    if not pdfs:
        pytest.skip(
            "Native-layout fallback gate: add weak-text CSE PDFs under tests/fixtures/fallback/"
        )
    for pdf_path in pdfs:
        document = extract_document_ir(pdf_path)
        assert document.quality.extraction_method
        token_count = sum(len(line.tokens) for page in document.pages for line in page.lines)
        assert token_count > 0
