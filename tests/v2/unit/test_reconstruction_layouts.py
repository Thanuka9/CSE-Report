from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import ExtractionMode
from cse_financial_etl.v2.document.router import merge_native_and_ocr_pages
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import canonical_document_from_pages, geometric_document


def test_two_column_group_company_keeps_both_value_cells() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"), (300.0, "Group")),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "1,000"), (340.0, "2,000")),
            ((40.0, "Revenue"), (220.0, "5,000"), (340.0, "8,000")),
        )
    )
    statement = build_statements(document)[0]
    assert len(statement.columns) == 2
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    assert [cell.parsed_numeric_value for cell in pat.cells] == [Decimal("1000"), Decimal("2000")]
    assert [cell.source_ref.raw_text for cell in pat.cells] == ["1,000", "2,000"]


def test_four_column_current_comparative_layout() -> None:
    document = geometric_document(
        (
            ((120.0, "Company"), (280.0, "Company"), (400.0, "Group"), (520.0, "Group")),
            (
                (120.0, "30 June 2026"),
                (280.0, "30 June 2025"),
                (400.0, "30 June 2026"),
                (520.0, "30 June 2025"),
            ),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "100"),
                (280.0, "90"),
                (400.0, "200"),
                (520.0, "180"),
            ),
            (
                (40.0, "Revenue"),
                (120.0, "500"),
                (280.0, "450"),
                (400.0, "800"),
                (520.0, "700"),
            ),
        )
    )
    statement = build_statements(document)[0]
    assert len(statement.columns) == 4
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    assert [cell.parsed_numeric_value for cell in pat.cells] == [
        Decimal("100"),
        Decimal("90"),
        Decimal("200"),
        Decimal("180"),
    ]


def test_percent_column_does_not_collapse_monetary_cells() -> None:
    document = geometric_document(
        (
            ((120.0, "Current"), (280.0, "Comparative"), (400.0, "Change %")),
            (
                (40.0, "Profit for the period"),
                (120.0, "3174532"),
                (280.0, "2728017"),
                (400.0, "16.37"),
            ),
            (
                (40.0, "Revenue"),
                (120.0, "24000000"),
                (280.0, "20000000"),
                (400.0, "20.00"),
            ),
        )
    )
    statement = build_statements(document)[0]
    assert len(statement.columns) == 3
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    assert [cell.parsed_numeric_value for cell in pat.cells] == [
        Decimal("3174532"),
        Decimal("2728017"),
        Decimal("16.37"),
    ]


def test_cell_source_ref_uses_numeric_token_not_full_line() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    statement = build_statements(document)[0]
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    cell = pat.cells[0]
    assert cell.raw_text == "1,234"
    assert cell.source_ref.raw_text == "1,234"
    assert "Profit for the period" not in (cell.source_ref.raw_text or "")
    assert pat.source_refs[0].raw_text.startswith("Profit for the period")


def test_p1_merge_replaces_empty_page_only() -> None:
    native = canonical_document_from_pages((("Heading",), ("placeholder",)))
    empty_page = native.pages[1].model_copy(update={"lines": ()})
    mixed = native.model_copy(update={"pages": (native.pages[0], empty_page)})
    ocr_page = native.pages[1].model_copy(update={"extraction_mode": ExtractionMode.OCR})
    merged = merge_native_and_ocr_pages(mixed, {2: ocr_page})
    assert merged.pages[0].extraction_mode is ExtractionMode.NATIVE
    assert merged.pages[1].extraction_mode is ExtractionMode.OCR
    assert [page.page_number for page in merged.pages] == [1, 2]
    assert merged.parser_manifest["page_routing"] == "page"
    assert merged.parser_manifest["extraction_mode"] == ExtractionMode.HYBRID.value
    assert merged.parser_manifest["ocr_pages"] == "2"
