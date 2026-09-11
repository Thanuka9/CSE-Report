from __future__ import annotations

from cse_financial_etl.document.continuation import detect_continuations
from cse_financial_etl.document.document_ir import (
    BBox,
    CanonicalDocumentIR,
    DocumentQuality,
    LineIR,
    PageIR,
    TokenIR,
)
from cse_financial_etl.document.region_detector import StatementRegion, detect_regions


def _page(page_number: int, lines: list[str]) -> PageIR:
    line_irs: list[LineIR] = []
    tokens: list[TokenIR] = []
    for line_index, text in enumerate(lines):
        y0 = 40.0 + line_index * 14.0
        line_tokens: list[TokenIR] = []
        x0 = 30.0
        for word in text.split():
            x1 = x0 + max(8.0, len(word) * 5.0)
            token = TokenIR(
                text=word,
                bbox=BBox(x0, y0, x1, y0 + 10.0),
                page_number=page_number,
            )
            line_tokens.append(token)
            tokens.append(token)
            x0 = x1 + 5.0
        if line_tokens:
            line_irs.append(
                LineIR(
                    tokens=tuple(line_tokens),
                    bbox=BBox(30.0, y0, x0, y0 + 10.0),
                    text=text,
                    page_number=page_number,
                    line_id=f"p{page_number}-l{line_index}",
                )
            )
    return PageIR(
        page_number=page_number,
        width=600.0,
        height=840.0,
        tokens=tuple(tokens),
        lines=tuple(line_irs),
    )


def _document(*pages: PageIR) -> CanonicalDocumentIR:
    token_count = sum(len(page.tokens) for page in pages)
    numeric_count = sum(
        1 for page in pages for token in page.tokens if any(ch.isdigit() for ch in token.text)
    )
    return CanonicalDocumentIR(
        pages=tuple(pages),
        quality=DocumentQuality(
            page_count=len(pages),
            token_count=token_count,
            numeric_token_count=numeric_count,
            text_page_ratio=1.0,
            extraction_method="native",
            requires_ocr=False,
        ),
        source_sha256="test-sha",
    )


def _strong_profit_page() -> PageIR:
    return _page(
        1,
        [
            "Statement of Profit or Loss",
            "Group Company",
            "Rs. 000",
            "Three months ended 30 June 2026 30 June 2025",
            "Revenue 100 90 80 70",
            "Profit 20 18 16 14",
        ],
    )


def _strong_company_profit_page() -> PageIR:
    return _page(
        1,
        [
            "Statement of Profit or Loss - Company",
            "For the three months ended 30 June 2026",
            "Rs. 000",
            "30 June 2026 30 June 2025",
            "Revenue 100 90",
            "Operating profit 20 18",
        ],
    )


def _untitled_company_continuation(*, marker: bool = True, year: int = 2026) -> PageIR:
    lines = [
        "Company",
        f"For the three months ended 30 June {year}",
        "Rs. 000",
        f"30 June {year} 30 June {year - 1}",
        "Profit before tax 20 18",
        "Profit for the period 16 14",
    ]
    if marker:
        lines.append("Continued from the preceding statement page")
    return _page(2, lines)


def test_weak_adjacent_page_cannot_borrow_strong_region_confidence() -> None:
    weak = _page(
        2,
        [
            "Revenue 100 90 80 70",
            "Expenses 50 45 40 35",
            "Profit 20 18 16 14",
        ],
    )
    regions = detect_regions(_document(_strong_profit_page(), weak))

    assert [(region.page_start, region.page_end) for region in regions] == [(1, 1), (2, 2)]
    assert regions[0].confidence == 0.9
    assert regions[1].confidence == 0.45


def test_source_evidenced_continuation_can_be_promoted_but_not_to_heading_confidence() -> None:
    continuation = _page(
        2,
        [
            "Group Company",
            "Rs. 000",
            "Three months ended 30 June 2026 30 June 2025",
            "Operating profit 30 25 20 15",
            "Tax 8 7 6 5",
        ],
    )
    regions = detect_regions(_document(_strong_profit_page(), continuation))

    assert len(regions) == 1
    assert regions[0].page_start == 1
    assert regions[0].page_end == 2
    assert regions[0].confidence == 0.8
    assert "continuation:" in regions[0].evidence


def test_explicit_marker_can_promote_an_other_page_to_prior_statement_identity() -> None:
    regions = detect_regions(
        _document(_strong_company_profit_page(), _untitled_company_continuation())
    )

    assert len(regions) == 1
    assert regions[0].statement_type == "PROFIT_LOSS"
    assert regions[0].page_start == 1
    assert regions[0].page_end == 2
    assert regions[0].confidence == 0.8
    assert "continuation:DATE+ENTITY+UNIT" in regions[0].evidence


def test_unclassified_page_without_marker_cannot_borrow_statement_identity() -> None:
    regions = detect_regions(
        _document(
            _strong_company_profit_page(),
            _untitled_company_continuation(marker=False),
        )
    )

    assert len(regions) == 2
    assert regions[1].statement_type == "OTHER"
    assert regions[1].confidence == 0.2


def test_continuation_marker_cannot_override_conflicting_source_dates() -> None:
    regions = detect_regions(
        _document(
            _strong_company_profit_page(),
            _untitled_company_continuation(year=2024),
        )
    )

    assert len(regions) == 2
    assert regions[1].statement_type == "OTHER"


def test_low_confidence_is_not_continuation_evidence() -> None:
    second = _page(2, ["Revenue 100 90 80 70", "Profit 20 18 16 14"])
    document = _document(_strong_profit_page(), second)
    regions = [
        StatementRegion("PROFIT_LOSS", 1, 1, "heading", 0.9),
        StatementRegion("PROFIT_LOSS", 2, 2, "numeric heuristic", 0.45),
    ]

    links = detect_continuations(document, regions)

    assert len(links) == 1
    assert not links[0].evidenced
    assert links[0].reason == "adjacent_same_type_unconfirmed"
