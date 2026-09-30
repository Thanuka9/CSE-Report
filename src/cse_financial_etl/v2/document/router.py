"""Document reader routing. OCR is used only when native text is absent."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalPage
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.canonicalize import canonicalize_document
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.document.ocr_reader import read_ocr_page, read_ocr_pdf, require_ocr_engine
from cse_financial_etl.v2.document.quality import DocumentQualityFeatures, measure_document_quality
from cse_financial_etl.v2.exceptions import NativeParseError, OcrRouteNotEnabledError

PageRouting = Literal["document", "page"]


def _empty_page_numbers(document: CanonicalDocument) -> tuple[int, ...]:
    return tuple(
        page.page_number
        for page in document.pages
        if sum(len(line.tokens) for line in page.lines) == 0
    )


def select_reader_route(features: DocumentQualityFeatures | None = None) -> ExtractionMode:
    """Scan-like empty native text routes to OCR. Token-count competition is forbidden."""

    if features is not None and features.native_token_count == 0:
        return ExtractionMode.OCR
    return ExtractionMode.NATIVE


def merge_native_and_ocr_pages(
    native: CanonicalDocument,
    ocr_pages: dict[int, CanonicalPage],
) -> CanonicalDocument:
    """Replace empty native pages with OCR pages. Never pick a parser for more tokens."""

    for number, page in ocr_pages.items():
        if page.page_number != number:
            raise NativeParseError("OCR replacement page_number must match the native page")
        if page.extraction_mode is not ExtractionMode.OCR:
            raise NativeParseError("page-level replacements must be OCR pages")
    pages = tuple(ocr_pages.get(page.page_number, page) for page in native.pages)
    manifest = dict(native.parser_manifest)
    manifest["page_routing"] = "page"
    if ocr_pages:
        manifest["extraction_mode"] = ExtractionMode.HYBRID.value
        ordered = ",".join(str(number) for number in sorted(ocr_pages))
        manifest["ocr_pages"] = ordered
        manifest["ocr_required_pages"] = ordered
    else:
        manifest["ocr_required_pages"] = ""
    return canonicalize_document(
        filing_version_id=native.filing_version_id,
        source_sha256=native.source_sha256,
        pages=pages,
        parser_manifest=manifest,
    )


def apply_page_level_routing(
    native: CanonicalDocument,
    pdf_path: Path,
) -> CanonicalDocument:
    """P1 diagnostic: OCR only pages with zero native tokens. Production stays P0."""

    empty = _empty_page_numbers(native)
    if not empty:
        manifest = dict(native.parser_manifest)
        manifest["page_routing"] = "page"
        manifest["ocr_required_pages"] = ""
        return native.model_copy(update={"parser_manifest": dict(sorted(manifest.items()))})
    try:
        engine = require_ocr_engine()
    except OcrRouteNotEnabledError:
        manifest = dict(native.parser_manifest)
        manifest["page_routing"] = "page"
        manifest["ocr_required_pages"] = ",".join(str(number) for number in empty)
        manifest["ocr_status"] = OcrRouteNotEnabledError.reason_code
        return native.model_copy(update={"parser_manifest": dict(sorted(manifest.items()))})
    replacements = {
        number: read_ocr_page(pdf_path, number, tesseract=engine) for number in empty
    }
    return merge_native_and_ocr_pages(native, replacements)


def read_document(
    pdf_path: Path,
    *,
    filing_version_id: str,
    force_ocr: bool = False,
    page_routing: PageRouting = "document",
) -> CanonicalDocument:
    if force_ocr:
        return read_ocr_pdf(pdf_path, filing_version_id=filing_version_id)
    native = read_native_pdf(pdf_path, filing_version_id=filing_version_id)
    if page_routing == "page":
        return apply_page_level_routing(native, pdf_path)
    route = select_reader_route(measure_document_quality(native))
    if route is ExtractionMode.OCR:
        return read_ocr_pdf(pdf_path, filing_version_id=filing_version_id)
    return native


def read_document_with_quality(
    pdf_path: Path, *, filing_version_id: str
) -> tuple[CanonicalDocument, DocumentQualityFeatures]:
    document = read_document(pdf_path, filing_version_id=filing_version_id)
    return document, measure_document_quality(document)
