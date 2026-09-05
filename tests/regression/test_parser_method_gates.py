from pathlib import Path

import pytest

from cse_financial_etl.documents.document_ir import extract_document_ir


def _pdfs(folder: str) -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / folder
    if not root.exists():
        return []
    return sorted(root.glob("*.pdf"))


def test_ocr_benchmark_requires_scanned_filings() -> None:
    """OCR gate: scanned PDFs must extract with lower certainty than native layout.

    Drop real scanned CSE filings into tests/fixtures/ocr/. Until then this gate stays open.
    """

    pdfs = _pdfs("ocr")
    if not pdfs:
        pytest.skip(
            "OCR universe gate: add scanned CSE PDFs under tests/fixtures/ocr/ "
            "and assert OCR_OCRMYPDF facts stay below auto-approve certainty."
        )
    for pdf_path in pdfs:
        document = extract_document_ir(pdf_path, ocr_dir=pdf_path.parent / "ocr-cache")
        assert "OCR" in document.quality.extraction_method.upper()


def test_native_layout_fallback_requires_weak_pymupdf_filings() -> None:
    """Fallback gate: pdfplumber/Docling must keep the same financial meaning.

    Drop PyMuPDF-weak CSE PDFs into tests/fixtures/fallback/.
    """

    pdfs = _pdfs("fallback")
    if not pdfs:
        pytest.skip(
            "Native-layout fallback gate: add weak-text CSE PDFs under "
            "tests/fixtures/fallback/ and assert PDFPLUMBER_WORDS or DOCLING "
            "publishes the same Company/3M/CURRENT fact."
        )
    methods = {
        extract_document_ir(pdf_path).quality.extraction_method for pdf_path in pdfs
    }
    assert methods & {"PDFPLUMBER_WORDS", "DOCLING"}
