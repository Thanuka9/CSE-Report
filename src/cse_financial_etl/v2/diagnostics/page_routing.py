"""Per-page native/OCR routing signals. Diagnostic only; production router stays P0."""

from __future__ import annotations

from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalPage
from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.quality import is_numeric_token


def page_native_token_count(page: CanonicalPage) -> int:
    return sum(len(line.tokens) for line in page.lines)


def page_numeric_token_count(page: CanonicalPage) -> int:
    return sum(1 for line in page.lines for token in line.tokens if is_numeric_token(token))


def classify_page_route(page: CanonicalPage) -> ExtractionMode:
    return ExtractionMode.OCR if page_native_token_count(page) == 0 else ExtractionMode.NATIVE


def mixed_native_ocr_document(document: CanonicalDocument) -> bool:
    routes = {classify_page_route(page) for page in document.pages}
    return ExtractionMode.NATIVE in routes and ExtractionMode.OCR in routes
