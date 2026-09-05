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
    METRIC_RULES,
    ExtractedFact,
    _find_metric,
    _is_dual_entity,
    _is_exact_quarter_page,
    _layout_candidates,
    _numbers,
    _page_entity_confidence,
    _page_statement_map,
    _select_current,
    _selected_eps_fact,
)


def test_company_column_wins_on_dual_entity_page() -> None:
    page = PdfPage(
        1,
        "Statement of comprehensive income\nGroup Company\nFor the quarter ended 30 June\n2026 2025 2026 2025",
    )
    values = _numbers("Profit for the period 10,113,665 5,063,588 8,187,022 4,011,546")
    assert _select_current(values, page, "FLOW") == ("8,187,022", Decimal("8187022"))


def test_change_column_is_not_mistaken_for_company_value() -> None:
    page = PdfPage(
        1,
        "Statement of profit or loss - Company/Group\nGroup Company\n"
        "For the three months ended 30 June\n2026 2025 Change 2026 2025 Change\nRs. Rs. % Rs. Rs. %",
    )
    values = _numbers(
        "Profit for the period 150,089,386 149,290,150 1% 108,959,808 165,084,378 -34%"
    )
    assert _select_current(values, page, "FLOW") == ("108,959,808", Decimal("108959808"))


def test_bank_balance_sheet_selects_bank_not_change_percentage() -> None:
    page = PdfPage(
        1,
        "Statement of financial position\nGroup Bank\n30.06.2026 30.06.2025 Change 30.06.2026 30.06.2025 Change\nRs.'000 % Rs.'000 %",
    )
    values = _numbers(
        "Total Assets 3,739,565,733 3,378,864,406 10.68 3,592,606,230 3,257,948,212 10.27"
    )
    assert _select_current(values, page, "STOCK") == ("3,592,606,230", Decimal("3592606230"))


def test_annual_only_page_is_not_an_exact_quarter() -> None:
    annual = PdfPage(1, "Statement of profit or loss\nFor the year ended 31 December 2025")
    quarter = PdfPage(
        2,
        "Statement of profit or loss\nFor the three months ended 31 December 2025",
    )
    assert not _is_exact_quarter_page(annual)
    assert _is_exact_quarter_page(quarter)


def test_generic_earnings_per_share_maps_to_basic() -> None:
    page = PdfPage(
        1,
        "Statement of profit or loss - Company\nFor the quarter ended 30 June 2026\n"
        "Company\nRs.\nEarnings per share (Rs.) 1.25 0.90",
    )
    basic_rule = next(rule for rule in METRIC_RULES if rule.code == "EPS_BASIC")
    assert _find_metric(page, basic_rule) == (
        "1.25",
        Decimal("1.25"),
        "Earnings per share (Rs.) 1.25 0.90",
    )


def _token(text: str, x: float, y: float, width: float = 40, height: float = 10) -> TokenIR:
    return TokenIR(text, BBox(x, y, x + width, y + height), 0, 0, 0)


def _line(page: int, y: float, tokens: list[TokenIR]) -> LineIR:
    bbox = BBox(
        min(token.bbox.x0 for token in tokens),
        min(token.bbox.y0 for token in tokens),
        max(token.bbox.x1 for token in tokens),
        max(token.bbox.y1 for token in tokens),
    )
    return LineIR(
        page, f"p{page}-{y}", " ".join(token.text for token in tokens), bbox, tuple(tokens)
    )


def _page(number: int, lines: list[LineIR], width: float = 800, height: float = 1000) -> PageIR:
    return PageIR(number, width, height, tuple(lines), "\n".join(line.text for line in lines))


def _document(pages: list[PageIR]) -> DocumentIR:
    return DocumentIR(
        "memory.pdf",
        tuple(pages),
        DocumentQuality(len(pages), 10, 4, 1.0, "TEST", False),
    )


def _eps_fact(code: str, value: str, status: str) -> ExtractedFact:
    extracted = status in {"EXTRACTED", "LOW_CERTAINTY"}
    amount = Decimal(value) if extracted else None
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        metric_code=code,
        metric_type="MONETARY_PER_SHARE",
        raw_text=value if extracted else None,
        raw_value=amount,
        normalized_value=amount,
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=2,
        source_line=code,
        unit_source_text="Rs.",
        confidence="HIGH" if extracted else "NONE",
        status=status,
        duration_months=3,
        validation_status="PASSED" if extracted else "FAILED",
        review_status="APPROVED" if extracted else "REVIEW",
        overall_certainty=0.9 if extracted else 0.0,
        evidence_json="{}",
    )


def test_dual_entity_headers_below_title_band_are_still_company() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Consolidated", 40, 20, 90),
                    _token("Statement", 140, 20, 70),
                    _token("of", 220, 20, 20),
                    _token("Profit", 250, 20, 50),
                    _token("or", 310, 20, 20),
                    _token("Loss", 340, 20, 40),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("For", 40, 40),
                    _token("the", 90, 40),
                    _token("three", 140, 40),
                    _token("months", 200, 40),
                    _token("ended", 270, 40),
                    _token("30", 330, 40, 20),
                    _token("June", 360, 40),
                    _token("2026", 420, 40),
                ],
            ),
            _line(1, 300, [_token("Group", 180, 300, 50), _token("Company", 480, 300, 60)]),
            _line(
                1,
                320,
                [
                    _token("2026", 180, 320),
                    _token("2025", 260, 320),
                    _token("2026", 480, 320),
                    _token("2025", 560, 320),
                ],
            ),
            _line(
                1,
                450,
                [
                    _token("Profit", 40, 450),
                    _token("for", 90, 450, 25),
                    _token("the", 125, 450, 25),
                    _token("period", 160, 450, 50),
                    _token("10,000", 180, 450, 50),
                    _token("8,000", 260, 450, 50),
                    _token("6,000", 480, 450, 50),
                    _token("4,000", 560, 450, 50),
                ],
            ),
        ],
    )
    assert _is_dual_entity(page)
    assert _page_entity_confidence(page, "COMPANY") > 0
    pat_rule = next(rule for rule in METRIC_RULES if rule.code == "PAT")
    candidates, _outside, wrong_scope = _layout_candidates(
        _document([page]), pat_rule, "COMPANY", date(2026, 6, 30)
    )
    assert not wrong_scope
    assert candidates
    assert candidates[0].raw_value == Decimal("6000")


def test_untitled_continuation_page_keeps_profit_or_loss_context() -> None:
    titled = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 120, 20, 20),
                    _token("profit", 150, 20, 50),
                    _token("or", 210, 20, 20),
                    _token("loss", 240, 20, 40),
                    _token("-", 290, 20, 10),
                    _token("Company", 310, 20, 60),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("For", 40, 40),
                    _token("the", 90, 40),
                    _token("three", 140, 40),
                    _token("months", 200, 40),
                    _token("ended", 270, 40),
                    _token("30", 330, 40, 20),
                    _token("June", 360, 40),
                    _token("2026", 420, 40),
                ],
            ),
        ],
    )
    continuation = _page(
        2,
        [
            _line(
                2,
                80,
                [
                    _token("Revenue", 40, 80, 70),
                    _token("100", 200, 80, 40),
                    _token("90", 280, 80, 40),
                ],
            )
        ],
    )
    document = _document([titled, continuation])
    assert _page_statement_map(document)[2] == "FLOW"
    top_line = next(rule for rule in METRIC_RULES if rule.code == "TOP_LINE")
    candidates, _outside, _wrong = _layout_candidates(
        document, top_line, "COMPANY", date(2026, 6, 30)
    )
    assert candidates
    assert candidates[0].raw_value == Decimal("100")
    assert candidates[0].page.number == 2


def test_eps_notes_page_prefers_diluted_company_column() -> None:
    income = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Consolidated", 40, 20, 90),
                    _token("Statement", 140, 20, 70),
                    _token("of", 220, 20, 20),
                    _token("Profit", 250, 20, 50),
                    _token("or", 310, 20, 20),
                    _token("Loss", 340, 20, 40),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("For", 40, 40),
                    _token("the", 90, 40),
                    _token("quarter", 140, 40),
                    _token("ended", 220, 40),
                    _token("30", 280, 40, 20),
                    _token("June", 310, 40),
                    _token("2026", 370, 40),
                ],
            ),
            _line(1, 80, [_token("Group", 180, 80, 50), _token("Company", 480, 80, 60)]),
        ],
    )
    notes = _page(
        3,
        [
            _line(
                3,
                40,
                [
                    _token("Earnings", 40, 40, 70),
                    _token("/(loss)", 120, 40, 50),
                    _token("per", 180, 40, 30),
                    _token("share", 220, 40, 40),
                ],
            ),
            _line(3, 70, [_token("Group", 180, 70, 50), _token("Company", 480, 70, 60)]),
            _line(
                3,
                90,
                [
                    _token("2026", 180, 90),
                    _token("2025", 260, 90),
                    _token("2026", 480, 90),
                    _token("2025", 560, 90),
                ],
            ),
            _line(
                3,
                130,
                [
                    _token("Basic", 40, 130, 50),
                    _token("2.00", 180, 130, 40),
                    _token("1.00", 260, 130, 40),
                    _token("1.50", 480, 130, 40),
                    _token("0.80", 560, 130, 40),
                ],
            ),
            _line(
                3,
                160,
                [
                    _token("Diluted", 40, 160, 55),
                    _token("1.90", 180, 160, 40),
                    _token("0.95", 260, 160, 40),
                    _token("1.40", 480, 160, 40),
                    _token("0.75", 560, 160, 40),
                ],
            ),
        ],
    )
    document = _document([income, notes])
    period = date(2026, 6, 30)
    basic_rule = next(rule for rule in METRIC_RULES if rule.code == "EPS_BASIC")
    diluted_rule = next(rule for rule in METRIC_RULES if rule.code == "EPS_DILUTED")
    basic, _outside, wrong_basic = _layout_candidates(document, basic_rule, "COMPANY", period)
    diluted, _outside_d, wrong_diluted = _layout_candidates(
        document, diluted_rule, "COMPANY", period
    )
    assert not wrong_basic
    assert not wrong_diluted
    assert basic
    assert diluted
    assert basic[0].raw_value == Decimal("1.50")
    assert diluted[0].raw_value == Decimal("1.40")
    selected = _selected_eps_fact(
        "Acme PLC",
        "ACME.N0000",
        period,
        "COMPANY",
        diluted=_eps_fact("EPS_DILUTED", "1.40", "EXTRACTED"),
        basic=_eps_fact("EPS_BASIC", "1.50", "EXTRACTED"),
    )
    assert selected.metric_code == "EPS_SELECTED"
    assert selected.normalized_value == Decimal("1.40")
    assert selected.unit_source_text == "Diluted EPS selected"


def test_eps_selected_falls_back_to_basic_when_diluted_missing() -> None:
    selected = _selected_eps_fact(
        "Acme PLC",
        "ACME.N0000",
        date(2026, 6, 30),
        "COMPANY",
        diluted=_eps_fact("EPS_DILUTED", "1.40", "CONSOLIDATED_ONLY"),
        basic=_eps_fact("EPS_BASIC", "1.50", "EXTRACTED"),
    )
    assert selected.normalized_value == Decimal("1.50")
    assert selected.unit_source_text == "Basic EPS selected"


def test_bare_basic_without_eps_context_is_ignored() -> None:
    page = PdfPage(
        1,
        "Statement of profit or loss - Company\nFor the quarter ended 30 June 2026\n"
        "Basic 12,000 10,000",
    )
    basic_rule = next(rule for rule in METRIC_RULES if rule.code == "EPS_BASIC")
    assert _find_metric(page, basic_rule) is None


def test_ytd_and_quarter_pair_selects_current_quarter_role() -> None:
    page = PdfPage(
        1,
        "Statement of profit or loss - Company\n"
        "For the six months ended 30 June 2026 and three months ended 30 June 2026\n"
        "2026 2025 2026 2025",
    )
    values = _numbers("Profit for the period 100 80 40 30")
    assert _select_current(values, page, "FLOW") == ("40", Decimal("40"))


def test_unproven_text_columns_are_not_guessed() -> None:
    page = PdfPage(1, "Notes to the financial statements\nOther disclosures")
    values = _numbers("Unlabelled amounts 10 20 30")
    assert _select_current(values, page, "FLOW") is None


def test_eps_selected_missing_uses_parser_absence_code() -> None:
    selected = _selected_eps_fact(
        "Acme PLC",
        "ACME.N0000",
        date(2026, 6, 30),
        "COMPANY",
        diluted=_eps_fact("EPS_DILUTED", "1.40", "NOT_FOUND_BY_PARSER"),
        basic=_eps_fact("EPS_BASIC", "1.50", "NOT_FOUND_BY_PARSER"),
    )
    assert selected.metric_code == "EPS_SELECTED"
    assert selected.normalized_value is None
    assert selected.status == "NOT_FOUND_BY_PARSER"
