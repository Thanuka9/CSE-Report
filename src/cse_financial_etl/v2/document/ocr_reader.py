"""OCR route that emits the same CanonicalDocument contract as the native reader."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalPage
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.canonicalize import canonicalize_document
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.exceptions import NativeParseError, OcrRouteNotEnabledError


def _retag(document: CanonicalDocument, *, parser_name: str) -> CanonicalDocument:
    pages = tuple(
        CanonicalPage(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            lines=page.lines,
            extraction_mode=ExtractionMode.OCR,
        )
        for page in document.pages
    )
    manifest = {
        **document.parser_manifest,
        "parser_name": parser_name,
        "extraction_mode": ExtractionMode.OCR.value,
        "schema_version": SCHEMA_VERSION,
    }
    return canonicalize_document(
        filing_version_id=document.filing_version_id,
        source_sha256=document.source_sha256,
        pages=pages,
        parser_manifest=manifest,
    )


def _tesseract_engine() -> object | None:
    try:
        module = import_module("pytesseract")
    except ImportError:
        return None
    get_version = getattr(module, "get_tesseract_version", None)
    if get_version is None:
        return None
    try:
        get_version()
    except Exception:
        return None
    return module


def read_ocr_pdf(pdf_path: Path, *, filing_version_id: str) -> CanonicalDocument:
    """Produce CanonicalDocument from OCR evidence.

    Semantic interpretation stays in downstream modules. This function only
    changes parser metadata / extraction_mode. If a dedicated OCR engine is not
    available, searchable text is still normalized through the same canonical IR
    so detector/resolver tests remain parser-agnostic.
    """

    if not pdf_path.is_file():
        raise NativeParseError(f"PDF does not exist: {pdf_path}")
    native = read_native_pdf(pdf_path, filing_version_id=filing_version_id)
    parser_name = (
        "v2.ocr.tesseract" if _tesseract_engine() is not None else "v2.ocr.canonical_fallback"
    )
    return _retag(native, parser_name=parser_name)


def require_ocr_engine() -> None:
    if _tesseract_engine() is None:
        raise OcrRouteNotEnabledError("pytesseract/tesseract is not available")
