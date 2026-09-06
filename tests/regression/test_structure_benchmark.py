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
    _assemble_standalone_liabilities,
    _coalesce_spaced_thousands,
    _layout_candidates,
    _numbers,
    _select_current,
    extract_filing,
    extract_quarter_prices,
    facts_by_code,
)
from cse_financial_etl.storage.run_archive import MANIFESTS_DIRNAME, RUNS_DIRNAME
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
    return _write_pdf_pages(path, [text])


def _write_pdf_pages(path: Path, pages: list[str]) -> Path:
    document = fitz.open()
    for text in pages:
        page = document.new_page(width=595, height=842)
        page.insert_textbox(fitz.Rect(36, 36, 559, 806), text, fontsize=10, fontname="helv")
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    document.close()
    return path


def test_canonical_manifest_directory_is_plural() -> None:
    assert MANIFESTS_DIRNAME == "manifests"
    assert MANIFESTS_DIRNAME != "run_manifests"
    assert RUNS_DIRNAME == "runs"


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
    candidates, _outside, wrong, _unresolved = _layout_candidates(
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
    candidates, _outside, wrong, _unresolved = _layout_candidates(
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


def test_group_company_two_values_selects_company_not_group() -> None:
    page = PdfPage(
        1,
        "Statement of comprehensive income\nGroup Company\nFor the quarter ended 30 June 2025",
    )
    values = _numbers("Profit for the period 10,113,665 8,187,022")
    selected = _select_current(values, page, "FLOW")
    assert selected == ("8,187,022", Decimal("8187022"))


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
    basic, _outside, _wrong_b, _unresolved_b = _layout_candidates(
        document, basic_rule, "COMPANY", PERIOD
    )
    diluted, _outside_d, _wrong_d, _unresolved_d = _layout_candidates(
        document, diluted_rule, "COMPANY", PERIOD
    )
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


def test_highest_lowest_last_traded_prefers_last_traded(tmp_path: Path) -> None:
    """JAT-style rows list highest / lowest / last traded — never take the lowest first."""

    pdf = _write_pdf(
        tmp_path / "jat_price.pdf",
        "Share information\n"
        "Market price per share as at 30 June 2025\n"
        "Highest Lowest Last traded 45.00 8.50 39.80\n",
    )
    prices = extract_quarter_prices(pdf, "Acme PLC", ["ACM.N0000"], PERIOD)
    assert prices
    assert prices[0].value == Decimal("39.80")


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
    assert RUNS_DIRNAME == "runs"












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


def test_group_titled_dual_sofp_extracts_company_liabilities() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Consolidated", 40, 20, 80),
                    _token("Statement", 130, 20, 60),
                    _token("of", 200, 20, 20),
                    _token("Financial", 230, 20, 55),
                    _token("Position", 295, 20, 50),
                ],
            ),
            _line(1, 40, [_token("Group", 220, 40, 50), _token("Company", 520, 40, 60)]),
            _line(1, 60, [_token("2025", 220, 60, 36), _token("2025", 520, 60, 36)]),
            _line(
                1,
                200,
                [
                    _token("Total", 40, 200, 40),
                    _token("liabilities", 90, 200, 70),
                    _token("900,000", 220, 200, 50),
                    _token("200,000", 520, 200, 50),
                ],
            ),
        ],
    )
    rule = next(item for item in METRIC_RULES if item.code == "TOTAL_LIABILITIES")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert candidates
    assert candidates[0].raw_value == Decimal("200000")
    assert "900" not in str(candidates[0].raw_value)


def test_cash_flow_operating_profit_is_not_used(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "cash_flow_op.pdf",
        "Statement of profit or loss - Company\n"
        "For the three months ended 30 June 2025\n"
        "Rs.'000\n"
        "Revenue 500 400\n"
        "Profit for the period 80 70\n"
        "Statement of cash flows - Company\n"
        "Operating profit before working capital changes 999 888\n",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    operating = facts_by_code(facts)["OPERATING_PROFIT"]
    assert operating.raw_value != Decimal("999")
    assert operating.status not in {"EXTRACTED", "LOW_CERTAINTY"} or (
        operating.normalized_value != Decimal("999000")
    )


def test_total_liabilities_and_shareholders_funds_is_not_liabilities(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "liab_and_funds.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 500 400\n"
        "Total liabilities 200 180\n"
        "Total equity 300 220\n"
        "Total liabilities and shareholders' funds 500 400\n",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert liabilities.status == "EXTRACTED"
    assert liabilities.raw_value == Decimal("200")
    assert liabilities.normalized_value == Decimal("200000")


def test_singular_total_liability_is_extracted(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "total_liability.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 500 400\n"
        "Total equity 300 220\n"
        "Total Liability 200 180\n"
        "Total equity and liabilities 500 400\n",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert liabilities.status == "EXTRACTED"
    assert liabilities.raw_value == Decimal("200")


def test_ocr_sofp_posttion_title_still_binds_stock(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "posttion.pdf",
        "Statement of financial posttion - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 500 400\n"
        "Total equity 300 220\n"
        "Total liabilities 200 180\n",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    assets = facts_by_code(facts)["TOTAL_ASSETS"]
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert assets.status == "EXTRACTED"
    assert assets.raw_value == Decimal("500")
    assert liabilities.status == "EXTRACTED"
    assert liabilities.raw_value == Decimal("200")


def test_printed_current_and_noncurrent_do_not_publish_derived_liabilities(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "assembled_liabilities.pdf",
        "Statement of financial position - Company\n"
        "As at 30 June 2025\n"
        "Rs.'000\n"
        "Total assets 500 400\n"
        "Total equity 250 220\n"
        "Total non-current liabilities 50 40\n"
        "Total current liabilities 200 180\n",
    )
    facts = extract_filing(pdf, "Acme PLC", "ACM.N0000", PERIOD)
    liabilities = facts_by_code(facts).get("TOTAL_LIABILITIES")
    assert liabilities is None or liabilities.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}


def test_dual_sofp_assembles_company_not_group_subtotals() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 20),
                    _token("Financial", 140, 20, 55),
                    _token("Position", 200, 20, 50),
                ],
            ),
            _line(1, 40, [_token("Group", 220, 40, 50), _token("Company", 520, 40, 60)]),
            _line(1, 60, [_token("2025", 220, 60, 36), _token("2025", 520, 60, 36)]),
            _line(1, 80, [_token("Rs.", 40, 80, 20), _token("'000", 70, 80, 30)]),
            _line(
                1,
                180,
                [
                    _token("Total", 40, 180, 40),
                    _token("current", 85, 180, 50),
                    _token("liabilities", 140, 180, 70),
                    _token("900,000", 220, 180, 50),
                    _token("200,000", 520, 180, 50),
                ],
            ),
            _line(
                1,
                200,
                [
                    _token("Total", 40, 200, 40),
                    _token("non-current", 85, 200, 70),
                    _token("liabilities", 160, 200, 70),
                    _token("400,000", 220, 200, 50),
                    _token("50,000", 520, 200, 50),
                ],
            ),
        ],
    )
    assembled = _assemble_standalone_liabilities(
        _document([page]),
        "COMPANY",
        PERIOD,
        {1: "STOCK"},
        "Acme PLC",
        "ACM.N0000",
    )
    assert assembled is not None
    assert assembled.entity_scope == "COMPANY"
    assert assembled.raw_value == Decimal("250000")
    assert assembled.raw_value != Decimal("1300000")


def test_dual_group_only_subtotals_are_not_copied_to_company() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 20),
                    _token("Financial", 140, 20, 55),
                    _token("Position", 200, 20, 50),
                ],
            ),
            _line(1, 40, [_token("Group", 220, 40, 50), _token("Company", 520, 40, 60)]),
            _line(1, 60, [_token("2025", 220, 60, 36), _token("2025", 520, 60, 36)]),
            _line(1, 80, [_token("Rs.", 40, 80, 20), _token("'000", 70, 80, 30)]),
            _line(
                1,
                180,
                [
                    _token("Total", 40, 180, 40),
                    _token("current", 85, 180, 50),
                    _token("liabilities", 140, 180, 70),
                    _token("900,000", 220, 180, 50),
                ],
            ),
            _line(
                1,
                200,
                [
                    _token("Total", 40, 200, 40),
                    _token("non-current", 85, 200, 70),
                    _token("liabilities", 160, 200, 70),
                    _token("400,000", 220, 200, 50),
                ],
            ),
        ],
    )
    assembled = _assemble_standalone_liabilities(
        _document([page]),
        "COMPANY",
        PERIOD,
        {1: "STOCK"},
        "Acme PLC",
        "ACM.N0000",
    )
    assert assembled is None


def test_dual_group_operating_profit_is_not_selected_for_company() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 20),
                    _token("Profit", 140, 20, 40),
                    _token("or", 185, 20, 20),
                    _token("Loss", 210, 20, 30),
                ],
            ),
            _line(1, 40, [_token("Group", 220, 40, 50), _token("Company", 520, 40, 60)]),
            _line(
                1,
                60,
                [
                    _token("For", 40, 60, 25),
                    _token("the", 70, 60, 25),
                    _token("quarter", 100, 60, 50),
                    _token("ended", 155, 60, 40),
                    _token("30", 200, 60, 20),
                    _token("June", 225, 60, 30),
                    _token("2025", 260, 60, 36),
                ],
            ),
            _line(1, 80, [_token("Rs.", 40, 80, 20), _token("'000", 70, 80, 30)]),
            _line(
                1,
                160,
                [
                    _token("Operating", 40, 160, 60),
                    _token("profit", 105, 160, 40),
                    _token("10,000", 220, 160, 50),
                ],
            ),
            _line(
                1,
                180,
                [
                    _token("Profit", 40, 180, 40),
                    _token("before", 85, 180, 40),
                    _token("tax", 130, 180, 25),
                    _token("8,000", 220, 180, 50),
                    _token("3,000", 520, 180, 50),
                ],
            ),
        ],
    )
    rule = next(item for item in METRIC_RULES if item.code == "OPERATING_PROFIT")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert all(candidate.raw_value != Decimal("10000") for candidate in candidates)
    pbt_rule = next(item for item in METRIC_RULES if item.code == "PBT")
    pbt_candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), pbt_rule, "COMPANY", PERIOD
    )
    assert pbt_candidates
    assert pbt_candidates[0].raw_value == Decimal("3000")
    assert pbt_candidates[0].raw_value != Decimal("8000")


def test_numbers_above_label_selects_company_operating_profit() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 20),
                    _token("Profit", 140, 20, 40),
                    _token("or", 185, 20, 20),
                    _token("Loss", 210, 20, 30),
                ],
            ),
            _line(1, 40, [_token("Group", 220, 40, 50), _token("Company", 520, 40, 60)]),
            _line(
                1,
                60,
                [
                    _token("For", 40, 60, 25),
                    _token("the", 70, 60, 25),
                    _token("quarter", 100, 60, 50),
                    _token("ended", 155, 60, 40),
                    _token("30", 200, 60, 20),
                    _token("June", 225, 60, 30),
                    _token("2025", 260, 60, 36),
                ],
            ),
            _line(1, 80, [_token("Rs.", 40, 80, 20), _token("'000", 70, 80, 30)]),
            _line(
                1,
                158,
                [
                    _token("10,000", 220, 158, 50),
                    _token("3,000", 520, 158, 50),
                ],
            ),
            _line(
                1,
                162,
                [
                    _token("Profit/(loss)", 40, 162, 80),
                    _token("from", 125, 162, 30),
                    _token("operations", 160, 162, 60),
                ],
            ),
        ],
        height=200,
    )
    rule = next(item for item in METRIC_RULES if item.code == "OPERATING_PROFIT")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert candidates
    assert candidates[0].raw_value == Decimal("3000")
    assert candidates[0].raw_value != Decimal("10000")


def test_notes_total_assets_are_not_used_as_sofp(tmp_path: Path) -> None:
    pdf = _write_pdf_pages(
        tmp_path / "notes_sofp.pdf",
        [
            "NOTES TO THE FINANCIAL STATEMENTS\n"
            "Disposal of equity stake\n"
            "Identifiable assets and liabilities\n"
            "Company Group\n"
            "Total assets 1860345 4192813\n"
            "Total liabilities 900000 2000000\n",
            "Statement of financial position - Company\n"
            "As at 30 June 2025\n"
            "Rs.'000\n"
            "Total assets 500 400\n"
            "Total equity 200 180\n"
            "Total liabilities 300 220\n",
        ],
    )
    facts = extract_filing(pdf, "Ambeon Holdings PLC", "GREG.N0000", PERIOD)
    assets = facts_by_code(facts)["TOTAL_ASSETS"]
    liabilities = facts_by_code(facts)["TOTAL_LIABILITIES"]
    assert assets.status == "EXTRACTED"
    assert assets.raw_value == Decimal("500")
    assert assets.raw_value != Decimal("1860345")
    assert liabilities.raw_value == Decimal("300")


def test_spaced_thousands_are_coalesced_for_pat() -> None:
    merged = _coalesce_spaced_thousands(
        (
            _token("1", 300, 80, 8),
            _token(",", 310, 80, 4),
            _token("557", 316, 80, 24),
        )
    )
    assert len(merged) == 1
    assert merged[0].text == "1,557"
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 20),
                    _token("profit", 140, 20, 45),
                    _token("or", 190, 20, 20),
                    _token("loss", 215, 20, 30),
                    _token("-", 250, 20, 8),
                    _token("Company", 265, 20, 55),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("For", 40, 40, 25),
                    _token("the", 70, 40, 25),
                    _token("three", 100, 40, 35),
                    _token("months", 140, 40, 45),
                    _token("ended", 190, 40, 40),
                    _token("30", 235, 40, 18),
                    _token("June", 258, 40, 30),
                    _token("2025", 292, 40, 32),
                ],
            ),
            _line(
                1,
                80,
                [
                    _token("Profit", 40, 80, 40),
                    _token("for", 85, 80, 20),
                    _token("the", 110, 80, 20),
                    _token("period", 135, 80, 40),
                    _token("1", 300, 80, 8),
                    _token(",", 310, 80, 4),
                    _token("557", 316, 80, 24),
                ],
            ),
        ],
    )
    rule = next(item for item in METRIC_RULES if item.code == "PAT")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert candidates
    assert candidates[0].raw_value == Decimal("1557")
    assert candidates[0].raw_value != Decimal("1")


def test_wrong_year_sofp_is_rejected() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("NINE", 40, 20, 30),
                    _token("MONTHS", 75, 20, 50),
                    _token("ENDED", 130, 20, 45),
                    _token("31ST", 180, 20, 30),
                    _token("DECEMBER", 215, 20, 60),
                    _token("2021", 280, 20, 32),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("Company", 40, 40, 55),
                    _token("Statement", 100, 40, 60),
                    _token("of", 165, 40, 16),
                    _token("Financial", 185, 40, 55),
                    _token("Position", 245, 40, 50),
                ],
            ),
            _line(
                1,
                120,
                [
                    _token("Total", 40, 120, 35),
                    _token("assets", 80, 120, 40),
                    _token("24,824,640,336", 300, 120, 90),
                ],
            ),
        ],
    )
    rule = next(item for item in METRIC_RULES if item.code == "TOTAL_ASSETS")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert not candidates


def test_related_party_revenue_is_not_used_as_top_line() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Transactions", 40, 20, 80),
                    _token("with", 125, 20, 30),
                    _token("other", 160, 20, 35),
                    _token("Related", 200, 20, 50),
                    _token("Parties", 255, 20, 50),
                ],
            ),
            _line(
                1,
                80,
                [
                    _token("Revenue", 40, 80, 55),
                    _token("438", 300, 80, 30),
                    _token("100", 360, 80, 30),
                ],
            ),
        ],
    )
    rule = next(item for item in METRIC_RULES if item.code == "TOP_LINE")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert not candidates
    assert all(candidate.raw_value != Decimal("438") for candidate in candidates)


def test_overlay_total_equity_uses_dropped_true_row() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Company", 40, 20, 55),
                    _token("Statement", 100, 20, 60),
                    _token("of", 165, 20, 16),
                    _token("Financial", 185, 20, 55),
                    _token("Position", 245, 20, 50),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("As", 40, 40, 16),
                    _token("at", 60, 40, 16),
                    _token("30", 80, 40, 16),
                    _token("June", 100, 40, 30),
                    _token("2025", 135, 40, 32),
                ],
            ),
            _line(
                1,
                80,
                [
                    _token("Total", 40, 80, 35),
                    _token("assets", 80, 80, 40),
                    _token("24,824,640,336", 381, 80, 49),
                    _token("22,418,201,331", 483, 80, 49),
                ],
            ),
            _line(
                1,
                468,
                [
                    _token("Total", 50, 468, 15),
                    _token("Equity", 67, 468, 21),
                    _token("(4,311,614)", 395, 468, 35),
                    _token("(530,107)", 503, 468, 29),
                ],
            ),
            _line(
                1,
                482,
                [
                    _token("22,308,415,009", 381, 482, 49),
                    _token("21,442,986,932", 483, 482, 49),
                ],
            ),
            _line(1, 493, [_token("Non", 50, 493, 25), _token("Current", 78, 493, 45), _token("Liabilities", 128, 493, 55)]),
        ],
        height=700,
    )
    rule = next(item for item in METRIC_RULES if item.code == "TOTAL_EQUITY")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert candidates
    assert candidates[0].raw_value == Decimal("22308415009")
    assert candidates[0].raw_value != Decimal("-4311614")


def test_other_comprehensive_income_is_not_pat() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 20),
                    _token("profit", 140, 20, 45),
                    _token("or", 190, 20, 20),
                    _token("loss", 215, 20, 30),
                    _token("-", 250, 20, 8),
                    _token("Company", 265, 20, 55),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("For", 40, 40, 25),
                    _token("the", 70, 40, 25),
                    _token("three", 100, 40, 35),
                    _token("months", 140, 40, 45),
                    _token("ended", 190, 40, 40),
                    _token("30", 235, 40, 18),
                    _token("June", 258, 40, 30),
                    _token("2025", 292, 40, 32),
                ],
            ),
            _line(
                1,
                80,
                [
                    _token("Profit", 40, 80, 40),
                    _token("after", 85, 80, 30),
                    _token("Taxation", 120, 80, 50),
                    _token("227,723,921", 300, 80, 70),
                ],
            ),
            _line(
                1,
                100,
                [
                    _token("Other", 40, 100, 35),
                    _token("comprehensive", 80, 100, 80),
                    _token("income", 165, 100, 40),
                    _token("for", 210, 100, 20),
                    _token("the", 235, 100, 20),
                    _token("period", 260, 100, 40),
                    _token("337,673,318", 300, 100, 70),
                ],
            ),
        ],
    )
    rule = next(item for item in METRIC_RULES if item.code == "PAT")
    candidates, _outside, _wrong, _unresolved = _layout_candidates(
        _document([page]), rule, "COMPANY", PERIOD
    )
    assert candidates
    assert candidates[0].raw_value == Decimal("227723921")
    assert all(candidate.raw_value != Decimal("337673318") for candidate in candidates)


def test_ambeon_style_share_count_is_not_published_as_eps(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "ambeon_eps.pdf",
        "Statement of profit or loss - Company\n"
        "For the three months ended 30 June 2025\n"
        "Rs.\n"
        "Profit for the period 12,500 10,000\n"
        "Earnings/(Loss) per share (953,816) 1,705,987 3,845,157\n"
        "Net assets per share 10.50 9.80\n",
    )
    facts = extract_filing(pdf, "Ambeon Holdings PLC", "GREG.N0000", PERIOD)
    by_code = facts_by_code(facts)
    for code in ("EPS_BASIC", "EPS_SELECTED"):
        fact = by_code[code]
        assert fact.raw_value != Decimal("3845157")
        assert fact.raw_value != Decimal("1705987")
        assert fact.raw_value != Decimal("-953816")
        if fact.status in {"EXTRACTED", "LOW_CERTAINTY"}:
            assert fact.raw_value is not None
            assert abs(fact.raw_value) < 1000


def test_overlay_identity_after_selection_keeps_reconciling_equity() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Company", 40, 20, 55),
                    _token("Statement", 100, 20, 60),
                    _token("of", 165, 20, 16),
                    _token("Financial", 185, 20, 55),
                    _token("Position", 245, 20, 50),
                ],
            ),
            _line(
                1,
                40,
                [
                    _token("As", 40, 40, 16),
                    _token("at", 60, 40, 16),
                    _token("30", 80, 40, 16),
                    _token("June", 100, 40, 30),
                    _token("2025", 135, 40, 32),
                ],
            ),
            _line(1, 55, [_token("Rs.", 40, 55, 20)]),
            _line(
                1,
                80,
                [
                    _token("Total", 40, 80, 35),
                    _token("assets", 80, 80, 40),
                    _token("24,824,640,336", 381, 80, 49),
                    _token("22,418,201,331", 483, 80, 49),
                ],
            ),
            _line(
                1,
                468,
                [
                    _token("Total", 50, 468, 15),
                    _token("Equity", 67, 468, 21),
                    _token("(4,311,614)", 395, 468, 35),
                    _token("(530,107)", 503, 468, 29),
                ],
            ),
            _line(
                1,
                482,
                [
                    _token("22,308,415,009", 381, 482, 49),
                    _token("21,442,986,932", 483, 482, 49),
                ],
            ),
            _line(
                1,
                520,
                [
                    _token("Total", 40, 520, 35),
                    _token("current", 80, 520, 45),
                    _token("liabilities", 130, 520, 55),
                    _token("1,000,000,000", 381, 520, 49),
                    _token("900,000,000", 483, 520, 49),
                ],
            ),
            _line(
                1,
                540,
                [
                    _token("Total", 40, 540, 35),
                    _token("non-current", 80, 540, 60),
                    _token("liabilities", 150, 540, 55),
                    _token("1,516,225,327", 381, 540, 49),
                    _token("1,000,000,000", 483, 540, 49),
                ],
            ),
        ],
        height=700,
    )
    document = _document([page])
    assets = _layout_candidates(
        document, next(item for item in METRIC_RULES if item.code == "TOTAL_ASSETS"), "COMPANY", PERIOD
    )[0]
    equity = _layout_candidates(
        document, next(item for item in METRIC_RULES if item.code == "TOTAL_EQUITY"), "COMPANY", PERIOD
    )[0]
    assembled = _assemble_standalone_liabilities(
        document,
        "COMPANY",
        PERIOD,
        {1: "STOCK"},
        "Windforce PLC",
        "WIND.N0000",
    )
    assert assets
    assert equity
    assert assets[0].raw_value == Decimal("24824640336")
    assert equity[0].raw_value == Decimal("22308415009")
    assert assembled is not None
    assert assembled.raw_value == Decimal("2516225327")
    difference = abs(assets[0].raw_value - assembled.raw_value - equity[0].raw_value)
    assert difference <= max(abs(assets[0].raw_value) * Decimal("0.02"), Decimal("1"))


def test_current_and_noncurrent_liabilities_do_not_publish_without_total_row(
    tmp_path: Path,
) -> None:
    pdf = _write_pdf_pages(
        tmp_path / "ambeon_liab.pdf",
        [
            "Statement of financial position - Company\n"
            "As at 30 June 2025\n"
            "Rs.'000\n"
            "Total assets 1,000 900\n"
            "Total equity 400 380\n"
            "Current liabilities 250 240\n",
            "Statement of financial position - Company (continued)\n"
            "As at 30 June 2025\n"
            "Rs.'000\n"
            "Non-current liabilities 350 330\n",
        ],
    )
    facts = extract_filing(pdf, "Ambeon Holdings PLC", "GREG.N0000", PERIOD)
    liabilities = facts_by_code(facts).get("TOTAL_LIABILITIES")
    assert liabilities is None or liabilities.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}


def test_closing_market_price_label_is_extracted(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "closing_price.pdf",
        "Share information\n"
        "Market price as at 30 June 2025\n"
        "Closing market price 18.50\n",
    )
    prices = extract_quarter_prices(pdf, "Acme PLC", ["ACM.N0000"], PERIOD)
    assert prices
    assert prices[0].value == Decimal("18.50")
    assert prices[0].status == "EXTRACTED"


def test_unlabelled_section_totals_assemble_company_liabilities() -> None:
    page = _page(
        1,
        [
            _line(
                1,
                20,
                [
                    _token("Statement", 40, 20, 70),
                    _token("of", 115, 20, 16),
                    _token("Financial", 140, 20, 55),
                    _token("Position", 200, 20, 50),
                ],
            ),
            _line(1, 40, [_token("GROUP", 305, 40, 45), _token("COMPANY", 437, 40, 55)]),
            _line(
                1,
                55,
                [
                    _token("As", 40, 55, 16),
                    _token("at", 60, 55, 16),
                    _token("30", 80, 55, 16),
                    _token("June", 100, 55, 30),
                    _token("2025", 135, 55, 32),
                ],
            ),
            _line(1, 70, [_token("Rs.", 40, 70, 20), _token("000", 65, 70, 20)]),
            _line(
                1,
                100,
                [
                    _token("Total", 40, 100, 35),
                    _token("assets", 80, 100, 40),
                    _token("1,000", 305, 100, 40),
                    _token("600", 437, 100, 40),
                ],
            ),
            _line(
                1,
                120,
                [
                    _token("Total", 40, 120, 35),
                    _token("equity", 80, 120, 40),
                    _token("400", 305, 120, 40),
                    _token("250", 437, 120, 40),
                ],
            ),
            _line(
                1,
                160,
                [_token("Non-Current", 40, 160, 70), _token("Liabilities", 115, 160, 55)],
            ),
            _line(
                1,
                180,
                [
                    _token("Borrowings", 40, 180, 60),
                    _token("200", 305, 180, 40),
                    _token("80", 437, 180, 40),
                ],
            ),
            _line(1, 200, [_token("300", 305, 200, 40), _token("100", 437, 200, 40)]),
            _line(
                1,
                240,
                [_token("Current", 40, 240, 50), _token("Liabilities", 95, 240, 55)],
            ),
            _line(
                1,
                260,
                [
                    _token("Payables", 40, 260, 50),
                    _token("300", 305, 260, 40),
                    _token("250", 437, 260, 40),
                ],
            ),
            _line(1, 280, [_token("300", 305, 280, 40), _token("250", 437, 280, 40)]),
            _line(
                1,
                320,
                [
                    _token("Total", 40, 320, 35),
                    _token("Equity", 80, 320, 40),
                    _token("and", 125, 320, 25),
                    _token("Liabilities", 155, 320, 55),
                    _token("1,000", 305, 320, 40),
                    _token("600", 437, 320, 40),
                ],
            ),
        ],
    )
    assembled = _assemble_standalone_liabilities(
        _document([page]),
        "COMPANY",
        PERIOD,
        {1: "STOCK"},
        "Ambeon Holdings PLC",
        "GREG.N0000",
    )
    assert assembled is not None
    assert assembled.raw_value == Decimal("350")
    assert assembled.raw_value != Decimal("600")
    assert assembled.status == "EXTRACTED_DERIVED"


def test_continuing_operations_is_not_pat_when_total_exists(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "continuing_pat.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 31 December 2025\n"
        "Rs. 000\n"
        "Profit/(Loss) for the Period from Continuing Operations (25,698)\n"
        "Profit/(Loss) for the period from discontinued operations 557,775\n"
        "Profit/(Loss) for the period 532,077\n",
    )
    facts = facts_by_code(extract_filing(pdf, "Ambeon Holdings PLC", "GREG.N0000", date(2025, 12, 31)))
    pat = facts["PAT"]
    assert pat.status == "EXTRACTED"
    assert pat.raw_value == Decimal("532077")
    assert pat.raw_value != Decimal("-25698")
    assert "Continuing" not in (pat.source_line or "")


def test_total_comprehensive_income_is_not_top_line(tmp_path: Path) -> None:
    pdf = _write_pdf_pages(
        tmp_path / "tci_top_line.pdf",
        [
            "AMBEON CAPITAL PLC\n"
            "Interim Financial Statements for the Quarter ended 31st December 2025\n"
            "Statement of profit or loss - Company\n"
            "For the Quarter Ended 31st December 2025\n"
            "Rs. 000\n"
            "Revenue - -\n"
            "Profit /(Loss) Before Tax 3,845,157\n"
            "Profit/(Loss) for the period 3,845,157\n",
            "AMBEON CAPITAL PLC\n"
            "Interim Financial Statements for the Quarter ended 31st December 2025\n"
            "Statement of other comprehensive income - Company\n"
            "Total Comprehensive Income for the Period 3,845,157\n",
        ],
    )
    facts = facts_by_code(
        extract_filing(pdf, "Ambeon Capital PLC", "TAP.N0000", date(2025, 12, 31))
    )
    top = facts["TOP_LINE"]
    assert top.raw_value != Decimal("3845157")
    assert "Comprehensive" not in (top.source_line or "")


def test_period_ended_ytd_page_does_not_beat_quarter_pnl(tmp_path: Path) -> None:
    pdf = _write_pdf_pages(
        tmp_path / "ytd_vs_quarter.pdf",
        [
            "AMBEON CAPITAL PLC\n"
            "Interim Financial Statements for the Quarter ended 31st December 2025\n"
            "Statement of profit or loss - Company\n"
            "For the Quarter Ended 31st December 2025\n"
            "Rs. 000\n"
            "Profit /(Loss) Before Tax 3,845,157\n"
            "Profit/(Loss) for the period 3,845,157\n",
            "AMBEON CAPITAL PLC\n"
            "Interim Financial Statements for the Quarter ended 31st December 2025\n"
            "Statement of profit or loss - Company\n"
            "For the Period Ended 31st December 2025\n"
            "Rs. 000\n"
            "Profit /(Loss) Before Tax from Continuing Operations 4,504,370\n"
            "Profit/(Loss) for the period 4,194,256\n",
        ],
    )
    facts = facts_by_code(
        extract_filing(pdf, "Ambeon Capital PLC", "TAP.N0000", date(2025, 12, 31))
    )
    pbt = facts["PBT"]
    assert pbt.status == "EXTRACTED"
    assert pbt.raw_value == Decimal("3845157")
    assert pbt.raw_value != Decimal("4504370")
    operating = facts["OPERATING_PROFIT"]
    assert operating.raw_value != Decimal("4504370")
    assert "Continuing Operations" not in (operating.source_line or "")


def test_wrapped_operating_profit_before_taxes_on_financial_services(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "wrapped_op.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 30 June 2026\n"
        "Rs.\n"
        "Interest income 100 90\n"
        "Operating Profit before Taxes on\n"
        "Financial Services 864,602,560 991,300,992\n"
        "Profit before Taxation from\n"
        "Operations 607,960,455 719,607,928\n"
        "Profit for the year 352,617,063 407,130,483\n",
    )
    facts = facts_by_code(
        extract_filing(pdf, "Alliance Finance Company PLC", "ALLI.N0000", date(2026, 6, 30))
    )
    assert facts["OPERATING_PROFIT"].status == "EXTRACTED"
    assert facts["OPERATING_PROFIT"].raw_value == Decimal("864602560")
    assert facts["PBT"].raw_value == Decimal("607960455")


def test_profit_from_operation_singular_is_operating_profit(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "profit_from_operation.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 30 June 2026\n"
        "Rs. 000\n"
        "Revenue 519,982 443,940\n"
        "Profit from Operation 165,706 102,339\n"
        "Profit Before Tax 168,372 110,216\n"
        "Profit for the year 88,091 76,641\n",
    )
    facts = facts_by_code(
        extract_filing(pdf, "Bogala Graphite Lanka PLC", "BOGA.N0000", date(2026, 6, 30))
    )
    operating = facts["OPERATING_PROFIT"]
    assert operating.status == "EXTRACTED"
    assert operating.raw_value == Decimal("165706")


def test_comprehensive_expense_income_is_not_top_line(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "comprehensive_expense.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 30 June 2026\n"
        "Rs.\n"
        "Interest Income 1,809,733,270 2,443,968,528\n"
        "(Loss)/ Profit for the period (2,809,621,335) 1,407,090,117\n"
        "Total Comprehensive (Expense)/ Income for the period (2,809,621,335) 1,407,090,117\n",
    )
    facts = facts_by_code(
        extract_filing(pdf, "Capital Alliance PLC", "CALT.N0000", date(2026, 6, 30))
    )
    top = facts["TOP_LINE"]
    assert "Comprehensive" not in (top.source_line or "")
    assert top.raw_value in {Decimal("1809733270"), Decimal("330218321")}


def test_other_operating_income_is_not_top_line(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "other_op_income.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 30 June 2026\n"
        "Rs. 000\n"
        "Revenue from contract with customers - -\n"
        "Total revenue - -\n"
        "Other operating income 131,052 90,158\n"
        "Result from operating activities 2,048,510 1,367,178\n"
        "Net profit for the Period 2,077,843 1,408,986\n",
    )
    facts = facts_by_code(
        extract_filing(pdf, "Vallibel One PLC", "VONE.N0000", date(2026, 6, 30))
    )
    top = facts["TOP_LINE"]
    assert top.raw_value != Decimal("131052")
    assert "Other operating" not in (top.source_line or "")
    pat = facts["PAT"]
    assert "continuing" not in (pat.source_line or "").lower()
    assert pat.raw_value == Decimal("2077843")


def test_continuing_operation_singular_is_not_preferred_pat(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "continuing_singular.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 30 June 2026\n"
        "Rs. 000\n"
        "Loss for the period from continuing operation (88,037) (77,374)\n"
        "Loss for the period (88,037) (77,374)\n",
    )
    facts = facts_by_code(
        extract_filing(pdf, "Palm Garden Hotels PLC", "PALM.N0000", date(2026, 6, 30))
    )
    pat = facts["PAT"]
    assert pat.status == "EXTRACTED"
    assert "continuing" not in (pat.source_line or "").lower()
    assert pat.raw_value == Decimal("-88037")


def test_split_three_months_header_is_exact_quarter_not_ytd(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "split_three_months.pdf",
        "Company Statements of Comprehensive Income\n"
        "Three Three Variance Nine months to Nine months Variance\n"
        "months to months to % to %\n"
        "31 December 2025 2024 2025 2024\n"
        "Rs.\n"
        "Revenue 5,816.61 5,892.91 (1.29) 15,362.42 15,883.94 (3.28)\n"
        "Profit for the period 100.00 90.00 11.11 300.00 280.00 7.14\n",
    )
    facts = facts_by_code(
        extract_filing(pdf, "C I C HOLDINGS PLC", "CIC.N0000", date(2025, 12, 31))
    )
    top = facts["TOP_LINE"]
    assert top.status == "EXTRACTED"
    assert top.raw_value == Decimal("5816.61")
    assert top.raw_value != Decimal("15362.42")


def test_earning_share_label_extracts_basic_eps(tmp_path: Path) -> None:
    pdf = _write_pdf(
        tmp_path / "earning_share.pdf",
        "Statement of profit or loss - Company\n"
        "For the quarter ended 31 December 2025\n"
        "Rs.\n"
        "Earning share 0.25 0.11\n",
    )
    facts = facts_by_code(extract_filing(pdf, "Windforce PLC", "WIND.N0000", date(2025, 12, 31)))
    eps = facts["EPS_BASIC"]
    assert eps.status == "EXTRACTED"
    assert eps.raw_value == Decimal("0.25")
