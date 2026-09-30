"""OCR route that emits the same CanonicalDocument contract as the native reader."""

from __future__ import annotations

import os
import tempfile
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pymupdf as fitz

from cse_financial_etl.v2 import PARSER_NAME_OCR, PARSER_VERSION_OCR, SCHEMA_VERSION
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalPage, CanonicalToken
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.canonicalize import canonicalize_document
from cse_financial_etl.v2.document.native_reader import _cluster_tokens, sha256_file
from cse_financial_etl.v2.exceptions import NativeParseError, OcrRouteNotEnabledError

_OCR_ZOOM = 2.0


def _tesseract_engine() -> Any | None:
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


def require_ocr_engine() -> Any:
    engine = _tesseract_engine()
    if engine is None:
        raise OcrRouteNotEnabledError(
            f"{OcrRouteNotEnabledError.reason_code}: pytesseract/tesseract is not available"
        )
    return engine


def _canonical_ocr_page(page: Any, *, page_number: int, tesseract: Any) -> CanonicalPage:
    rect = page.rect
    tokens = _ocr_page_tokens(page, page_number=page_number, tesseract=tesseract)
    return CanonicalPage(
        page_number=page_number,
        width=float(rect.width),
        height=float(rect.height),
        lines=_cluster_tokens(tokens, page_number=page_number),
        extraction_mode=ExtractionMode.OCR,
    )


def read_ocr_page(
    pdf_path: Path,
    page_number: int,
    *,
    tesseract: Any | None = None,
) -> CanonicalPage:
    """OCR a single PDF page. Does not retag native text as OCR."""

    if not pdf_path.is_file():
        raise NativeParseError(f"PDF does not exist: {pdf_path}")
    if page_number < 1:
        raise NativeParseError("page_number must be >= 1")
    engine = tesseract or require_ocr_engine()
    try:
        with fitz.open(pdf_path) as document:  # type: ignore[no-untyped-call]
            page_count = int(document.page_count)
            if page_number > page_count:
                raise NativeParseError(f"page {page_number} is out of range for {pdf_path}")
            page = document.load_page(page_number - 1)
            return _canonical_ocr_page(page, page_number=page_number, tesseract=engine)
    except OcrRouteNotEnabledError:
        raise
    except NativeParseError:
        raise
    except Exception as exc:
        raise NativeParseError(
            f"OCR failed to parse page {page_number} of {pdf_path}: {exc}"
        ) from exc


def _ocr_page_tokens(page: Any, *, page_number: int, tesseract: Any) -> list[CanonicalToken]:
    matrix = fitz.Matrix(_OCR_ZOOM, _OCR_ZOOM)  # type: ignore[no-untyped-call]
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    handle, raw_path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    png_path = Path(raw_path)
    try:
        pixmap.save(str(png_path))
        data = tesseract.image_to_data(str(png_path), output_type=tesseract.Output.DICT)
    finally:
        png_path.unlink(missing_ok=True)
    tokens: list[CanonicalToken] = []
    count = len(data.get("text") or ())
    for index in range(count):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            conf_raw = float(data["conf"][index])
        except (TypeError, ValueError, KeyError):
            conf_raw = -1.0
        confidence = None if conf_raw < 0 else conf_raw / 100.0
        left = float(data["left"][index])
        top = float(data["top"][index])
        width = float(data["width"][index])
        height = float(data["height"][index])
        x0, y0 = left / _OCR_ZOOM, top / _OCR_ZOOM
        x1, y1 = (left + width) / _OCR_ZOOM, (top + height) / _OCR_ZOOM
        tokens.append(
            CanonicalToken(
                text=text,
                page_number=page_number,
                bbox=(x0, y0, x1, y1),
                confidence=confidence,
                source_parser=PARSER_NAME_OCR,
            )
        )
    return tokens


def read_ocr_pdf(pdf_path: Path, *, filing_version_id: str) -> CanonicalDocument:
    """Rasterize each page and OCR it. Never retag native PyMuPDF text as OCR."""

    if not pdf_path.is_file():
        raise NativeParseError(f"PDF does not exist: {pdf_path}")
    tesseract = require_ocr_engine()
    source_sha256 = sha256_file(pdf_path)
    pages: list[CanonicalPage] = []
    try:
        with fitz.open(pdf_path) as document:  # type: ignore[no-untyped-call]
            page_count = int(document.page_count)
            if page_count < 1:
                raise NativeParseError("PDF contains no pages")
            for index in range(1, page_count + 1):
                page = document.load_page(index - 1)
                pages.append(_canonical_ocr_page(page, page_number=index, tesseract=tesseract))
    except OcrRouteNotEnabledError:
        raise
    except NativeParseError:
        raise
    except Exception as exc:
        raise NativeParseError(f"OCR failed to parse {pdf_path}: {exc}") from exc
    return canonicalize_document(
        filing_version_id=filing_version_id,
        source_sha256=source_sha256,
        pages=tuple(pages),
        parser_manifest={
            "schema_version": SCHEMA_VERSION,
            "parser_name": PARSER_NAME_OCR,
            "parser_version": PARSER_VERSION_OCR,
            "pymupdf_version": version("PyMuPDF"),
            "extraction_mode": ExtractionMode.OCR.value,
        },
    )
