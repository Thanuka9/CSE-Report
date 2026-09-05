from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pymupdf as fitz
import pytest

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
    _layout_candidates,
    _numbers,
    _select_current,
    extract_filing,
    extract_quarter_prices,
    facts_by_code,
)
from cse_financial_etl.storage.run_archive import MANIFESTS_DIRNAME
from cse_financial_etl.validation.benchmark import (
    CaseResult,
    ExpectedFact,
    FieldResult,
    check_extracted_fact,
    dashboard,
    write_dashboard,
)
from cse_financial_etl.validation.cross_filing import flag_cross_filing_mismatches

PERIOD = date(2025, 6, 30)
RESULTS: list = []


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
        DocumentQuality(len(pages), 40, 12, 1.0, "TEST", False),
    )


def _pat_rule():
    return next(rule for rule in METRIC_RULES if rule.code == "PAT")


def _record(result) -> None:
    RESULTS.append(result)
    assert result.passed, (
        f"{result.case_id} {result.failure_class}: "
        + "; ".join(
            f"{field.field} expected {field.expected} actual {field.actual}"
            for field in result.fields
            if not field.passed
        )
    )


def _fact_from_candidates(
    candidates: list,
    entity: str,
    period: date,
    *,
    metric_code: str = "PAT",
) -> ExtractedFact | None:
    if not candidates:
        return None
    selected = candidates[0]
    rejected = [str(item.raw_value) for item in candidates[1:]]
    column_values = [
        str(row.get("raw")) for row in selected.graph.get("column_scores", []) if row.get("raw")
    ]
    return ExtractedFact(
        issuer_name="JOHN KEELLS HOLDINGS PLC",
        symbol="JKH.N0000",
        period_end=period,
        metric_code=metric_code,
        metric_type="MONETARY_ABSOLUTE",
        raw_text=selected.token.text,
        raw_value=selected.raw_value,
        normalized_value=selected.raw_value,
        currency="LKR",
        scale_factor=1000,
        entity_scope=entity,
        source_page=selected.page.number,
        source_line=selected.line.text,
        unit_source_text="Rs.'000",
        confidence="HIGH",
        status="EXTRACTED",
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="APPROVED",
        evidence_json=json.dumps(
            {
                "source_header_year": period.year,
                "comparison_role": "CURRENT",
                "rejected_raw_values": rejected + column_values,
                "column_raw_values": column_values,
                "graph": selected.graph,
            },
            separators=(",", ":"),
        ),
    )


def _write_pdf(path: Path, text: str) -> Path:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_textbox(fitz.Rect(36, 36, 559, 806), text, fontsize=10, fontname="helv")
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()
    return path


def test_canonical_manifest_directory_is_plural() -> None:
    assert MANIFESTS_DIRNAME == "manifests"
    assert MANIFESTS_DIRNAME != "run_manifests"


def test_jkh_comparative_and_ytd_columns_are_rejected() -> None:
    xs = (160, 230, 310, 380, 470, 540, 620, 690)
    values = (
        "12,000",
        "11,000",
        "5,000",
        "4,000",
        "9,000",
        "8,000",
        "3,637,206",
        "764,265",
    )
    page = _page(
        1,
        [
            _line(1, 20, [_token("Statement", 40, 20, 70), _token("of", 120, 20, 20),
                          _token("profit", 150, 20, 50), _token("or", 210, 20, 20),
                          _token("loss", 240, 20, 40)]),
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
                    _token("2025", 420, 40),
                ],
            ),
            _line(1, 80, [_token("Group", 250, 80, 50), _token("Company", 560, 80, 60)]),
            _line(
                1,
                100,
                [
                    _token("Six", 140, 100, 25),
                    _token("months", 170, 100, 45),
                    _token("Three", 300, 100, 40),
                    _token("months", 345, 100, 45),
                    _token("Six", 450, 100, 25),
                    _token("months", 480, 100, 45),
                    _token("Three", 610, 100, 40),
                    _token("months", 655, 100, 45),
                ],
            ),
            _line(
                1,
                120,
                [_token("2025" if index % 2 == 0 else "2024", x, 120, 36) for index, x in enumerate(xs)],
            ),
            _line(
                1,
                200,
                [
                    _token("Profit", 40, 200, 45),
                    _token("for", 90, 200, 25),
                    _token("the", 120, 200, 25),
                    _token("period", 150, 200, 45),
                    *[_token(value, x, 200, 50) for value, x in zip(values, xs, strict=True)],
                ],
            ),
        ],
    )
    candidates, _outside, wrong = _layout_candidates(
        _document([page]), _pat_rule(), "COMPANY", PERIOD
    )
    assert not wrong
    fact = _fact_from_candidates(candidates, "COMPANY", PERIOD)
    discovered = {value.replace(",", "") for value in values}
    if fact is not None:
        discovered.update(str(item.raw_value).replace(",", "") for item in candidates)
        graph = json.loads(fact.evidence_json or "{}").get("graph", {})
        discovered.update(
            str(row.get("raw", "")).replace(",", "") for row in graph.get("column_scores", [])
        )
    _record(
        check_extracted_fact(
            case_id="jkh_ytd_vs_3m",
            family="JKH comparative/YTD",
            fact=fact,
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="3,637,206",
                normalized_value="3637206",
                source_page=1,
                unit_scale=1000,
                unit_currency="LKR",
                rejected_raw_values=("764265", "9000", "12000"),
            ),
            discovered=discovered,
        )
    )
    text_page = PdfPage(
        1,
        "Statement of profit or loss - Company\nGroup Company\n"
        "For the six months ended 30 June 2025 and three months ended 30 June 2025\n"
        "2025 2024 2025 2024 2025 2024 2025 2024\n"
        "Profit for the period 12,000 11,000 5,000 4,000 9,000 8,000 3,637,206 764,265",
    )
    selected = _select_current(_numbers("Profit for the period 12,000 11,000 5,000 4,000 9,000 8,000 3,637,206 764,265"), text_page, "FLOW")
    assert selected == ("3,637,206", Decimal("3637206"))


def test_parent_header_span_beats_nearer_six_month_label() -> None:
    """A 3M parent span owns the column even when a 6M token is closer."""

    xs = (160, 230, 310, 380, 470, 540, 620, 690)
    values = (
        "12,000",
        "11,000",
        "5,000",
        "4,000",
        "9,000",
        "8,000",
        "3,637,206",
        "764,265",
    )
    page = _page(
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
                    _token("2025", 420, 40),
                ],
            ),
            _line(1, 80, [_token("Group", 250, 80, 50), _token("Company", 560, 80, 60)]),
            _line(
                1,
                100,
                [
                    _token("Six", 140, 100, 25),
                    _token("months", 170, 100, 45),
                    _token("Three", 300, 100, 40),
                    _token("months", 345, 100, 45),
                    _token("Six", 450, 100, 25),
                    _token("months", 480, 100, 45),
                    _token("Three", 610, 100, 40),
                    _token("months", 655, 100, 45),
                ],
            ),
            _line(
                1,
                115,
                [_token("Six", 590, 115, 25), _token("months", 620, 115, 45)],
            ),
            _line(
                1,
                130,
                [_token("2025" if index % 2 == 0 else "2024", x, 130, 36) for index, x in enumerate(xs)],
            ),
            _line(
                1,
                200,
                [
                    _token("Profit", 40, 200, 45),
                    _token("for", 90, 200, 25),
                    _token("the", 120, 200, 25),
                    _token("period", 150, 200, 45),
                    *[_token(value, x, 200, 50) for value, x in zip(values, xs, strict=True)],
                ],
            ),
        ],
    )
    candidates, _outside, wrong = _layout_candidates(
        _document([page]), _pat_rule(), "COMPANY", PERIOD
    )
    assert not wrong
    assert candidates
    assert candidates[0].raw_value == Decimal("3637206")
    relations = {edge["relation"] for edge in candidates[0].graph.get("edges", [])}
    assert "PARENT_HEADER" in relations
    _record(
        check_extracted_fact(
            case_id="parent_span_over_nearest_6m",
            family="JKH comparative/YTD",
            fact=_fact_from_candidates(candidates, "COMPANY", PERIOD),
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="3,637,206",
                normalized_value="3637206",
                source_page=1,
                unit_scale=1000,
                unit_currency="LKR",
                rejected_raw_values=("9000", "764265"),
            ),
            discovered={value.replace(",", "") for value in values},
        )
    )


def test_group_company_selects_company_region() -> None:
    page = PdfPage(
        1,
        "Statement of comprehensive income\nGroup Company\nFor the quarter ended 30 June\n2025 2024 2025 2024",
    )
    values = _numbers("Profit for the period 10,113,665 5,063,588 8,187,022 4,011,546")
    selected = _select_current(values, page, "FLOW")
    assert selected == ("8,187,022", Decimal("8187022"))
    _record(
        check_extracted_fact(
            case_id="group_company",
            family="Group / Company",
            fact=ExtractedFact(
                "Acme PLC",
                "ACM.N0000",
                PERIOD,
                "PAT",
                "MONETARY_ABSOLUTE",
                selected[0],
                selected[1],
                selected[1],
                "LKR",
                1,
                "COMPANY",
                1,
                "Profit for the period",
                "Rs.",
                "HIGH",
                "EXTRACTED",
                comparison_role="CURRENT",
                duration_months=3,
                validation_status="PASSED",
                evidence_json=json.dumps(
                    {
                        "source_header_year": 2025,
                        "rejected_raw_values": ["10113665", "5063588", "4011546"],
                    }
                ),
            ),
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="8187022",
                normalized_value="8187022",
                rejected_raw_values=("10113665",),
            ),
        )
    )


def test_group_bank_selects_bank_region() -> None:
    page = PdfPage(
        1,
        "Statement of financial position\nGroup Bank\n30.06.2025 30.06.2024 Change 30.06.2025 30.06.2024 Change\nRs.'000 % Rs.'000 %",
    )
    selected = _select_current(
        _numbers("Total Assets 3,739,565,733 3,378,864,406 10.68 3,592,606,230 3,257,948,212 10.27"),
        page,
        "STOCK",
    )
    assert selected == ("3,592,606,230", Decimal("3592606230"))
    _record(
        check_extracted_fact(
            case_id="group_bank",
            family="Group / Bank",
            fact=ExtractedFact(
                "National Development Bank PLC",
                "NDB.N0000",
                PERIOD,
                "TOTAL_ASSETS",
                "MONETARY_ABSOLUTE",
                selected[0],
                selected[1],
                selected[1],
                "LKR",
                1000,
                "BANK",
                1,
                "Total Assets",
                "Rs.'000",
                "HIGH",
                "EXTRACTED",
                comparison_role="CURRENT",
                duration_months=None,
                validation_status="PASSED",
                evidence_json=json.dumps(
                    {"source_header_year": 2025, "rejected_raw_values": ["3739565733"]}
                ),
            ),
            expected=ExpectedFact(
                metric_code="TOTAL_ASSETS",
                entity_scope="BANK",
                period_end=PERIOD,
                source_year=2025,
                duration_months=None,
                comparison_role="CURRENT",
                raw_value="3592606230",
                normalized_value="3592606230",
                unit_scale=1000,
                unit_currency="LKR",
                rejected_raw_values=("3739565733",),
            ),
        )
    )


def test_reversed_company_group_is_not_positional() -> None:
    page = PdfPage(
        1,
        "Statement of profit or loss\nCompany Group\nFor the three months ended 30 June\n2025 2024 2025 2024",
    )
    values = _numbers("Profit for the period 6,000 4,000 10,000 8,000")
    selected = _select_current(values, page, "FLOW")
    assert selected == ("6,000", Decimal("6000"))
    _record(
        check_extracted_fact(
            case_id="reversed_company_group",
            family="Reversed Company / Group",
            fact=ExtractedFact(
                "Acme PLC",
                "ACM.N0000",
                PERIOD,
                "PAT",
                "MONETARY_ABSOLUTE",
                selected[0],
                selected[1],
                selected[1],
                "LKR",
                1,
                "COMPANY",
                1,
                "Profit for the period",
                "Rs.",
                "HIGH",
                "EXTRACTED",
                comparison_role="CURRENT",
                duration_months=3,
                validation_status="PASSED",
                evidence_json=json.dumps(
                    {"source_header_year": 2025, "rejected_raw_values": ["10000"]}
                ),
            ),
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="6000",
                normalized_value="6000",
                rejected_raw_values=("10000",),
            ),
        )
    )


@pytest.mark.parametrize(
    ("family_suffix", "header", "line", "expected_raw"),
    (
        (
            "2",
            "Company\nFor the quarter ended 30 June 2025\n2025 2024",
            "Profit for the period 400 300",
            "400",
        ),
        (
            "4",
            "Group Company\nFor the quarter ended 30 June 2025\n2025 2024 2025 2024",
            "Profit for the period 100 80 400 300",
            "400",
        ),
        (
            "6",
            "Group Company\nFor the three months ended 30 June\n2025 2024 Change 2025 2024 Change",
            "Profit for the period 150 140 1% 400 300 -2%",
            "400",
        ),
        (
            "8",
            "Group Company\nFor the six months ended 30 June 2025 and three months ended 30 June 2025\n"
            "2025 2024 2025 2024 2025 2024 2025 2024",
            "Profit for the period 120 110 50 40 90 80 400 300",
            "400",
        ),
    ),
)
def test_dynamic_column_counts_resolve_current_company(
    family_suffix: str, header: str, line: str, expected_raw: str
) -> None:
    page = PdfPage(1, f"Statement of profit or loss\n{header}")
    selected = _select_current(_numbers(line), page, "FLOW")
    assert selected is not None
    assert selected[0].replace(",", "") == expected_raw
    _record(
        check_extracted_fact(
            case_id=f"numeric_regions_{family_suffix}",
            family="2/4/6/8 numeric regions",
            fact=ExtractedFact(
                "Acme PLC",
                "ACM.N0000",
                PERIOD,
                "PAT",
                "MONETARY_ABSOLUTE",
                selected[0],
                selected[1],
                selected[1],
                "LKR",
                1,
                "COMPANY",
                1,
                line,
                "Rs.",
                "HIGH",
                "EXTRACTED",
                comparison_role="CURRENT",
                duration_months=3,
                validation_status="PASSED",
                evidence_json=json.dumps(
                    {
                        "source_header_year": 2025,
                        "rejected_raw_values": [item[0] for item in _numbers(line) if item[0] != selected[0]],
                    }
                ),
            ),
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value=expected_raw,
                normalized_value=expected_raw,
            ),
        )
    )


def test_eps_continuation_prefers_diluted() -> None:
    income = _page(
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
                    _token("2025", 420, 40),
                ],
            ),
        ],
    )
    notes = _page(
        2,
        [
            _line(
                2,
                40,
                [
                    _token("Earnings", 40, 40, 70),
                    _token("/(loss)", 120, 40, 50),
                    _token("per", 180, 40, 30),
                    _token("share", 220, 40, 40),
                ],
            ),
            _line(2, 80, [_token("Group", 180, 80, 50), _token("Company", 480, 80, 60)]),
            _line(
                2,
                100,
                [
                    _token("2025", 180, 100),
                    _token("2024", 260, 100),
                    _token("2025", 480, 100),
                    _token("2024", 560, 100),
                ],
            ),
            _line(
                2,
                140,
                [
                    _token("Basic", 40, 140, 45),
                    _token("1.90", 180, 140, 40),
                    _token("1.20", 260, 140, 40),
                    _token("1.50", 480, 140, 40),
                    _token("1.10", 560, 140, 40),
                ],
            ),
            _line(
                2,
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
    basic_rule = next(rule for rule in METRIC_RULES if rule.code == "EPS_BASIC")
    diluted_rule = next(rule for rule in METRIC_RULES if rule.code == "EPS_DILUTED")
    basic, _outside, _wrong_b = _layout_candidates(document, basic_rule, "COMPANY", PERIOD)
    diluted, _outside_d, _wrong_d = _layout_candidates(document, diluted_rule, "COMPANY", PERIOD)
    assert basic and diluted
    selected = ExtractedFact(
        "Acme PLC",
        "ACM.N0000",
        PERIOD,
        "EPS_SELECTED",
        "MONETARY_PER_SHARE",
        diluted[0].token.text,
        diluted[0].raw_value,
        diluted[0].raw_value,
        "LKR",
        1,
        "COMPANY",
        2,
        diluted[0].line.text,
        "Diluted EPS selected",
        "HIGH",
        "EXTRACTED",
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        evidence_json=json.dumps(
            {
                "source_header_year": 2025,
                "rejected_raw_values": [str(basic[0].raw_value)],
            }
        ),
    )
    _record(
        check_extracted_fact(
            case_id="eps_diluted_preferred",
            family="EPS continuation page",
            fact=selected,
            expected=ExpectedFact(
                metric_code="EPS_SELECTED",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="1.40",
                normalized_value="1.40",
                source_page=2,
                rejected_raw_values=("1.50",),
            ),
        )
    )


def test_statement_unit_is_inherited_when_away_from_row(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "units.pdf",
        "Statement of profit or loss - Company\n"
        "For the three months ended 30 June 2025\n"
        "Rs.'000\n"
        "Revenue 1,000 900\n"
        "Profit for the period 250 180\n",
    )
    facts = facts_by_code(extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD, ocr_enabled=False))
    pat = facts.get("PAT")
    _record(
        check_extracted_fact(
            case_id="unit_away_from_row",
            family="Unit away from row",
            fact=pat,
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="250",
                normalized_value="250000",
                unit_scale=1000,
                unit_currency="LKR",
            ),
        )
    )


def test_key_value_price_keeps_security_class(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "price.pdf",
        "Share information\n"
        "Market price per share\n"
        "Last traded 30 June 2025\n"
        "Voting ordinary shares ACM.N0000 20.20\n",
    )
    prices = extract_quarter_prices(pdf, "Acme PLC", ["ACM.N0000"], PERIOD)
    assert prices
    price = prices[0]
    assert price.symbol == "ACM.N0000"
    _record(
        check_extracted_fact(
            case_id="key_value_price",
            family="Key/value price disclosure",
            fact=ExtractedFact(
                price.issuer_name,
                price.symbol,
                price.period_end,
                "MARKET_PRICE_QUARTER_END",
                "MONETARY_PER_SHARE",
                str(price.value),
                price.value,
                price.value,
                "LKR",
                1,
                "COMPANY",
                price.source_page,
                price.source_line,
                "LKR/share",
                price.confidence,
                price.status,
                comparison_role="CURRENT",
                duration_months=None,
                validation_status=price.validation_status,
                evidence_json=json.dumps(
                    {"source_header_year": PERIOD.year, "source_method": price.source_method}
                ),
            ),
            expected=ExpectedFact(
                metric_code="MARKET_PRICE_QUARTER_END",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=None,
                comparison_role="CURRENT",
                raw_value="20.20",
                normalized_value="20.20",
            ),
        )
    )


def test_narrative_navps(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "navps.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 10,000\n"
        "Total equity 4,000\n"
        "Total liabilities 6,000\n"
        "Net assets per share 14.18\n",
    )
    facts = facts_by_code(extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD, ocr_enabled=False))
    navps = facts.get("NAVPS")
    _record(
        check_extracted_fact(
            case_id="narrative_navps",
            family="Narrative NAVPS",
            fact=navps,
            expected=ExpectedFact(
                metric_code="NAVPS",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=None,
                comparison_role="CURRENT",
                raw_value="14.18",
                normalized_value="14.18",
            ),
        )
    )


def test_missing_metric_distinguishes_parser_from_confirmed(tmp_path: Path) -> None:
    income = _write_pdf(
        tmp_path / "income.pdf",
        "Statement of profit or loss - Company\n"
        "For the three months ended 30 June 2025\n"
        "Rs.\n"
        "Revenue 1,000 900\n"
        "Profit before tax 400 300\n",
    )
    notes = _write_pdf(
        tmp_path / "notes.pdf",
        "Board of directors\nRegistered office Colombo\nCompany secretaries\nNo financial table on this page.\n",
    )
    income_facts = facts_by_code(
        extract_filing(income, "Acme PLC", "ACM.N0000", PERIOD, ocr_enabled=False)
    )
    notes_facts = facts_by_code(
        extract_filing(notes, "Acme PLC", "ACM.N0000", PERIOD, ocr_enabled=False)
    )
    income_pat = income_facts["PAT"]
    notes_pat = notes_facts["PAT"]
    assert income_pat.status == "SOURCE_CONFIRMED_NOT_REPORTED"
    assert notes_pat.status == "NOT_FOUND_BY_PARSER"
    RESULTS.append(
        CaseResult(
            "confirmed_missing_pat",
            "Missing metric",
            True,
            "PASS",
            [
                FieldResult("status", True, "SOURCE_CONFIRMED_NOT_REPORTED", income_pat.status),
                FieldResult("parser_status", True, "NOT_FOUND_BY_PARSER", notes_pat.status),
            ],
        )
    )
    assert notes_pat.status != income_pat.status


def test_restated_comparative_goes_to_review(tmp_path: Path) -> None:
    gold = tmp_path / "current_financial_facts.parquet"
    pl.DataFrame(
        {
            "issuer_name": ["Acme PLC"],
            "period_end": ["2025-06-30"],
            "metric_code": ["PAT"],
            "status": ["EXTRACTED"],
            "normalized_value": ["100"],
            "filing_sha256": ["oldhash"],
        }
    ).write_parquet(gold)
    from cse_financial_etl.sources.cse import DownloadedFiling, Filing

    filing = Filing(
        "Acme PLC",
        "ACM.N0000",
        1,
        PERIOD,
        "Q",
        "x.pdf",
        "https://example.invalid/x.pdf",
        None,
        None,
    )
    downloaded = DownloadedFiling(filing, tmp_path / "x.pdf", "newhash", 10)
    fact = ExtractedFact(
        "Acme PLC",
        "ACM.N0000",
        PERIOD,
        "PAT",
        "MONETARY_ABSOLUTE",
        "200",
        Decimal("200"),
        Decimal("200"),
        "LKR",
        1,
        "COMPANY",
        1,
        "PAT",
        "Rs.",
        "HIGH",
        "EXTRACTED",
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
    )
    mismatches = flag_cross_filing_mismatches([(downloaded, [fact])], gold)
    assert mismatches
    assert mismatches[0].metric_code == "PAT"
    _record(
        check_extracted_fact(
            case_id="restated_comparative",
            family="Restated comparative",
            fact=fact,
            expected=ExpectedFact(
                metric_code="PAT",
                entity_scope="COMPANY",
                period_end=PERIOD,
                source_year=2025,
                duration_months=3,
                comparison_role="CURRENT",
                raw_value="200",
                normalized_value="200",
            ),
        )
    )
    RESULTS[-1].detail = mismatches[0].detail
    assert "differs from prior filing" in mismatches[0].detail


def test_write_accuracy_dashboard() -> None:
    project_root = Path(__file__).resolve().parents[2]
    payload = dashboard(RESULTS)
    path = write_dashboard(project_root, payload)
    assert path.exists()
    assert payload["metrics"]["wrong_populated_value_rate"] == 0
    assert MANIFESTS_DIRNAME == "manifests"








def test_cumulative_only_flow_is_never_published_as_quarter(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "cumulative_only.pdf",
        "Statement of profit or loss - Company\n"
        "For the six months ended 30 June 2025\n"
        "Rs.'000\n"
        "Profit for the period 12,500 10,000",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    pat = facts_by_code(facts)["PAT"]
    assert pat.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}


def test_total_liabilities_is_never_assets_minus_equity_fallback(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "no_liabilities.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 300 250\n"
        "Total equity 100 90",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert liabilities.status != "EXTRACTED_DERIVED"
    assert liabilities.normalized_value is None
