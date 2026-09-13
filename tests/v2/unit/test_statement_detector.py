from __future__ import annotations

from pathlib import Path

import pymupdf as fitz

from cse_financial_etl.v2.contracts.enums import StatementType
from cse_financial_etl.v2.document.native_reader import read_native_pdf
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from tests.v2.helpers import canonical_document_from_pages


def test_statement_headings_are_detected() -> None:
    document = canonical_document_from_pages(
        (
            ("Example PLC", "Interim Financial Statements", "Quarter ended 30 June 2026"),
            (
                "Statement of profit or loss",
                "For the three months ended 30 June 2026",
                "Profit for the period 1,234",
            ),
            (
                "Statement of financial position",
                "As at 30 June 2026",
                "Total assets 9,876",
            ),
            (
                "Statement of cash flows",
                "For the three months ended 30 June 2026",
                "Net cash from operating activities 100",
            ),
            (
                "Statement of changes in equity",
                "For the three months ended 30 June 2026",
                "Balance at beginning of period 500",
            ),
            (
                "Earnings per share",
                "Basic earnings per share 2.50",
                "Diluted earnings per share 2.40",
            ),
        )
    )
    regions = detect_statement_regions(document)
    types = tuple(region.statement_type for region in regions)
    assert StatementType.INCOME_STATEMENT in types
    assert StatementType.BALANCE_SHEET in types
    assert StatementType.CASH_FLOW in types
    assert StatementType.CHANGES_IN_EQUITY in types
    assert StatementType.EPS_NOTE in types
    cover = next(region for region in regions if region.page_start == 1)
    assert cover.statement_type is StatementType.OTHER_FINANCIAL_STATEMENT
    income = next(
        region for region in regions if region.statement_type is StatementType.INCOME_STATEMENT
    )
    assert income.source_refs[0].page_number == 2
    assert "profit or loss" in income.source_refs[0].raw_text.lower()


def test_notes_mentioning_income_statement_are_not_income_pages() -> None:
    document = canonical_document_from_pages(
        (
            (
                "Notes to the financial statements",
                "1. Basis of preparation",
                "Profit for the period is as shown in the income statement.",
                "See the statement of financial position for total assets.",
            ),
        )
    )
    regions = detect_statement_regions(document)
    assert len(regions) == 1
    assert regions[0].statement_type is StatementType.OTHER_FINANCIAL_STATEMENT
    assert "NOTES_REGION" in regions[0].reason_codes


def test_contents_page_is_not_a_statement() -> None:
    document = canonical_document_from_pages(
        (
            (
                "Contents",
                "Statement of financial position .............. 2",
                "Statement of profit or loss .................... 3",
                "Statement of cash flows ........................ 4",
            ),
        )
    )
    regions = detect_statement_regions(document)
    assert regions[0].statement_type is StatementType.OTHER_FINANCIAL_STATEMENT
    assert "CONTENTS_PAGE" in regions[0].reason_codes


def test_index_of_multiple_titles_is_other() -> None:
    document = canonical_document_from_pages(
        (
            (
                "Statement of financial position .............. 2",
                "Statement of profit or loss .................... 3",
                "Statement of cash flows ........................ 4",
            ),
        )
    )
    regions = detect_statement_regions(document)
    assert regions[0].statement_type is StatementType.OTHER_FINANCIAL_STATEMENT
    assert "MULTI_STATEMENT_INDEX" in regions[0].reason_codes


def test_explicit_continuation_inherits_previous_statement() -> None:
    document = canonical_document_from_pages(
        (
            (
                "Statement of profit or loss",
                "For the three months ended 30 June 2026",
                "Revenue 100",
            ),
            (
                "Statement of profit or loss (continued)",
                "Operating expenses 40",
                "Profit for the period 60",
            ),
        )
    )
    regions = detect_statement_regions(document)
    income = [
        region for region in regions if region.statement_type is StatementType.INCOME_STATEMENT
    ]
    assert len(income) == 1
    assert income[0].page_start == 1
    assert income[0].page_end == 2
    assert "EXPLICIT_CONTINUATION" in income[0].reason_codes


def test_unlabelled_next_page_is_not_assumed_to_continue() -> None:
    document = canonical_document_from_pages(
        (
            ("Statement of profit or loss", "Profit for the period 60"),
            ("Operating expenses 40", "Other commentary without a statement title"),
        )
    )
    regions = detect_statement_regions(document)
    assert regions[0].statement_type is StatementType.INCOME_STATEMENT
    assert regions[0].page_end == 1
    assert regions[1].statement_type is StatementType.OTHER_FINANCIAL_STATEMENT


def test_numeric_density_does_not_invent_a_balance_sheet() -> None:
    document = canonical_document_from_pages(
        (
            (
                "Example PLC",
                "Total assets 100 Total equity 40 Total liabilities 60",
                "Non-current assets 70 Current assets 30",
            ),
        )
    )
    regions = detect_statement_regions(document)
    assert regions[0].statement_type is StatementType.OTHER_FINANCIAL_STATEMENT
    assert "HEADING_MATCH" not in regions[0].reason_codes


def test_native_pdf_statement_pages_are_detected(tmp_path: Path) -> None:
    pdf_path = tmp_path / "statements.pdf"
    document = fitz.open()
    pages = (
        ("INTERIM FINANCIAL STATEMENTS", "Example PLC"),
        (
            "Statement of profit or loss",
            "For the three months ended 30 June 2026",
            "Profit for the period 1,234",
        ),
        ("Statement of financial position", "As at 30 June 2026", "Total assets 9,876"),
        ("Notes to the financial statements", "Profit is as shown in the income statement"),
    )
    for lines in pages:
        page = document.new_page(width=612, height=792)
        y = 72.0
        for line in lines:
            page.insert_text((72, y), line)
            y += 16.0
    document.save(pdf_path)
    document.close()

    parsed = read_native_pdf(pdf_path, filing_version_id="fv-pdf")
    regions = detect_statement_regions(parsed)
    by_type = {region.statement_type for region in regions}
    assert StatementType.INCOME_STATEMENT in by_type
    assert StatementType.BALANCE_SHEET in by_type
    notes = [region for region in regions if "NOTES_REGION" in region.reason_codes]
    assert notes
    assert all(region.statement_type is StatementType.OTHER_FINANCIAL_STATEMENT for region in notes)
    for region in regions:
        assert region.source_refs
        assert region.source_refs[0].source_sha256 == parsed.source_sha256


def test_successive_headed_income_pages_are_not_merged() -> None:
    document = canonical_document_from_pages(
        (
            (
                "INCOME STATEMENT - GROUP",
                "For the quarter ended 30 June 2026",
                "Profit for the period 100",
            ),
            (
                "INCOME STATEMENT - BANK",
                "For the quarter ended 30 June 2026",
                "Profit for the period 80",
            ),
        )
    )
    regions = detect_statement_regions(document)
    income = [
        region for region in regions if region.statement_type is StatementType.INCOME_STATEMENT
    ]
    assert len(income) == 2
    assert income[0].page_start == 1
    assert income[1].page_start == 2
    assert "GROUP" in income[0].heading_text
    assert "BANK" in income[1].heading_text


def test_plural_statements_of_comprehensive_income_is_detected() -> None:
    document = canonical_document_from_pages(
        (
            ("DISTILLERIES COMPANY OF SRI LANKA PLC", "INTERIM FINANCIAL STATEMENTS"),
            (
                "DISTILLERIES COMPANY OF SRI LANKA PLC",
                "STATEMENTS OF COMPREHENSIVE INCOME",
                "Group Company",
                "For the Quarter ended 30th June 2026 2025 2026 2025",
                "Gross Revenue 100 90 80 70",
            ),
        )
    )
    regions = detect_statement_regions(document)
    types = [region.statement_type for region in regions]
    assert StatementType.INCOME_STATEMENT in types
    assert regions[0].statement_type is StatementType.OTHER_FINANCIAL_STATEMENT


def test_investor_information_page_is_eps_note() -> None:
    document = canonical_document_from_pages(
        (
            ("Hayleys PLC", "Interim Financial Statements"),
            (
                "INVESTOR INFORMATION",
                "30.06.2026 30.06.2025",
                "Last traded price 238.00 173.75",
                "RATIOS",
                "Net assets per share 148.27 127.14",
            ),
        )
    )
    regions = detect_statement_regions(document)
    assert any(region.statement_type is StatementType.EPS_NOTE for region in regions)
