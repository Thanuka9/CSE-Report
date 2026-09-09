import os
from pathlib import Path

import pytest

from cse_financial_etl.documents.document_ir import (
    BBox,
    LineIR,
    PageIR,
    TokenIR,
    extract_document_ir,
)


def _pdfs(folder: str) -> list[Path]:
    root = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / folder
    if not root.exists():
        return []
    return sorted(root.glob("*.pdf"))


def test_ocr_fixture_extracts_or_marks_ocr_path() -> None:
    """OCR gate: scanned/image PDFs must route through OCR when the runtime is installed."""

    pdfs = _pdfs("ocr")
    if not pdfs:
        pytest.skip("OCR universe gate: add scanned CSE PDFs under tests/fixtures/ocr/")
    require_real_ocr = os.environ.get("CSE_REQUIRE_REAL_OCR") == "1"
    for pdf_path in pdfs:
        document = extract_document_ir(pdf_path, ocr_dir=pdf_path.parent / "ocr-cache")
        method = (document.quality.extraction_method or "").upper()
        token_count = sum(len(line.tokens) for page in document.pages for line in page.lines)
        assert document.pages, "OCR fixture produced no pages"
        if require_real_ocr:
            assert "OCR" in method, (
                f"OCR runtime is mandatory but {pdf_path.name} ended with {method}; "
                f"requires_ocr={document.quality.requires_ocr} token_count={token_count}"
            )
            assert token_count > 0
        else:
            assert "OCR" in method or document.quality.requires_ocr or token_count == 0


def test_ocr_router_prefers_fresh_ocr_geometry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prove the OCR branch creates and selects fresh geometry, not a tagged old candidate."""

    from cse_financial_etl.documents import document_ir as module

    source = tmp_path / "scan.pdf"
    source.write_bytes(b"placeholder")
    derivative = tmp_path / "scan.ocr.pdf"
    derivative.write_bytes(b"placeholder-ocr")

    def page(token_count: int) -> PageIR:
        tokens = tuple(
            TokenIR(str(index + 1), BBox(float(index), 0.0, float(index + 1), 10.0), 0, 0, index)
            for index in range(token_count)
        )
        line = LineIR(1, "p1-r0", " ".join(token.text for token in tokens), BBox(0, 0, max(1, token_count), 10), tokens)
        return PageIR(1, 600, 800, (line,), line.text)

    monkeypatch.setattr(module, "_extract_pymupdf_pages", lambda path: [page(40)] if path == derivative else [page(1)])
    monkeypatch.setattr(module, "_extract_pdfplumber_pages", lambda path: [page(1)])
    monkeypatch.setattr(module, "_extract_docling_pages", lambda path: None)
    monkeypatch.setattr(module, "_ocr_derivative", lambda path, ocr_dir: derivative)

    document = extract_document_ir(source, ocr_dir=tmp_path / "cache", enable_ocr=True)
    assert document.quality.extraction_method == "OCR_OCRMYPDF"
    assert document.quality.token_count == 40
    assert not document.quality.requires_ocr


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
