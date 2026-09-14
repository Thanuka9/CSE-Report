from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.diagnostics.page_routing import (
    classify_page_route,
    empty_native_page_numbers,
    mixed_native_ocr_document,
    page_native_token_count,
)
from cse_financial_etl.v2.document.router import apply_page_level_routing
from cse_financial_etl.v2.exceptions import OcrRouteNotEnabledError
from tests.v2.helpers import canonical_document_from_pages, geometric_document


def test_page_router_signals_do_not_change_p0_document_route() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    assert classify_page_route(document.pages[0]) is ExtractionMode.NATIVE
    assert page_native_token_count(document.pages[0]) > 0
    assert mixed_native_ocr_document(document) is False


def test_empty_page_is_ocr_candidate() -> None:
    native = canonical_document_from_pages((("Heading",),))
    empty = canonical_document_from_pages((("x",),))
    empty_page = empty.pages[0].model_copy(update={"lines": (), "page_number": 2})
    mixed = native.model_copy(update={"pages": (native.pages[0], empty_page)})
    assert classify_page_route(empty_page) is ExtractionMode.OCR
    assert mixed_native_ocr_document(mixed) is True
    assert empty_native_page_numbers(mixed) == (2,)


def test_p1_without_ocr_records_empty_pages_and_does_not_invent_tokens() -> None:
    native = canonical_document_from_pages((("Heading",), ("x",)))
    empty_page = native.pages[1].model_copy(update={"lines": ()})
    mixed = native.model_copy(update={"pages": (native.pages[0], empty_page)})
    with patch(
        "cse_financial_etl.v2.document.router.require_ocr_engine",
        side_effect=OcrRouteNotEnabledError("OCR_REQUIRED_NOT_AVAILABLE: test"),
    ):
        routed = apply_page_level_routing(mixed, Path("unused.pdf"))
    assert routed.pages[1].lines == ()
    assert routed.parser_manifest["page_routing"] == "page"
    assert routed.parser_manifest["ocr_required_pages"] == "2"
    assert routed.parser_manifest.get("ocr_status") == "OCR_REQUIRED_NOT_AVAILABLE"
    assert "page_routing" not in (native.parser_manifest or {})
