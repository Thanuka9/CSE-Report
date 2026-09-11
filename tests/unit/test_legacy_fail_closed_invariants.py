from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.documents.document_ir import (
    BBox,
    DocumentIR,
    DocumentQuality,
    LineIR,
    PageIR,
    TokenIR,
)
from cse_financial_etl.documents.pdf_text import PdfPage
from cse_financial_etl.extraction.statement_extractor import (
    ExtractedFact,
    MetricRule,
    _comparison_from_layout,
    _missing_fact,
    _page_statement_map,
    _select_current,
    _unit_for_layout,
    facts_by_code,
)


def _token(text: str, x: float, y: float) -> TokenIR:
    return TokenIR(text, BBox(x, y, x + 40, y + 10), 0, 0, 0)


def _line(page: int, y: float, *tokens: TokenIR) -> LineIR:
    return LineIR(
        page,
        f"p{page}-{y}",
        " ".join(token.text for token in tokens),
        BBox(10, y, 500, y + 10),
        tuple(tokens),
    )


def _page(number: int, *lines: LineIR) -> PageIR:
    return PageIR(number, 600, 800, tuple(lines), "\n".join(line.text for line in lines))


def _doc(*pages: PageIR) -> DocumentIR:
    return DocumentIR(
        "memory.pdf",
        tuple(pages),
        DocumentQuality(len(pages), 10, 3, 1.0, "TEST", False),
    )


def _fact(code: str, value: str) -> ExtractedFact:
    amount = Decimal(value)
    return ExtractedFact(
        issuer_name="Example PLC",
        symbol="EX.N0000",
        period_end=date(2026, 6, 30),
        metric_code=code,
        metric_type="MONETARY_ABSOLUTE",
        raw_text=value,
        raw_value=amount,
        normalized_value=amount,
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line=code,
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
    )


def test_extracted_fact_has_no_implicit_current_role() -> None:
    assert _fact("PAT", "10").comparison_role == "UNKNOWN"


def test_missing_flow_fact_has_no_invented_three_month_duration() -> None:
    rule = MetricRule("PAT", (), "FLOW", "MONETARY_ABSOLUTE")
    missing = _missing_fact(
        "Example PLC",
        "EX.N0000",
        date(2026, 6, 30),
        rule,
        "COMPANY",
        "NOT_FOUND_BY_PARSER",
    )
    assert missing.duration_months is None


def test_layout_role_is_unknown_without_source_date_headers() -> None:
    value = _token("100", 300, 100)
    row = _line(1, 100, _token("Revenue", 20, 100), value)
    role, _ = _comparison_from_layout(
        _page(1, row),
        row,
        value,
        date(2026, 6, 30),
        entity="COMPANY",
    )
    assert role == "UNKNOWN"


def test_single_value_is_not_current_without_period_evidence() -> None:
    page = PdfPage(1, "Statement of profit or loss\nRevenue 100")
    assert _select_current([("100", Decimal("100"))], page, "FLOW") is None


def test_untitled_page_without_repeated_header_does_not_inherit_statement() -> None:
    first = _page(
        1,
        _line(
            1,
            20,
            _token("Statement", 20, 20),
            _token("of", 70, 20),
            _token("profit", 100, 20),
            _token("or", 160, 20),
            _token("loss", 190, 20),
        ),
    )
    second = _page(
        2,
        _line(2, 80, _token("Revenue", 20, 80), _token("100", 300, 80)),
    )
    assert _page_statement_map(_doc(first, second))[2] is None


def test_per_share_currency_is_not_invented_without_source_unit() -> None:
    row = _line(
        1,
        100,
        _token("Basic", 20, 100),
        _token("EPS", 70, 100),
        _token("1.25", 300, 100),
    )
    page = _page(1, row)
    assert _unit_for_layout(
        _doc(page),
        page,
        row,
        "MONETARY_PER_SHARE",
    ) == (None, None, None, 0.0)


def test_per_share_currency_can_use_same_page_source_declaration() -> None:
    unit = _line(1, 30, _token("Rs.", 20, 30))
    row = _line(
        1,
        100,
        _token("Basic", 20, 100),
        _token("EPS", 70, 100),
        _token("1.25", 300, 100),
    )
    page = _page(1, unit, row)
    currency, scale, source, confidence = _unit_for_layout(
        _doc(page),
        page,
        row,
        "MONETARY_PER_SHARE",
    )
    assert currency == "LKR"
    assert scale == 1
    assert source is not None
    assert confidence > 0


def test_duplicate_metric_facts_do_not_use_last_write_wins() -> None:
    mapping = facts_by_code(
        [_fact("PAT", "10"), _fact("PAT", "11"), _fact("PBT", "12")]
    )
    assert "PAT" not in mapping
    assert mapping["PBT"].raw_value == Decimal("12")
