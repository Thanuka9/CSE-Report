from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.v2.statements.numeric import parse_numeric
from cse_financial_etl.v2.statements.statement_builder import build_statements
from tests.v2.helpers import geometric_document


def test_reconstructed_cells_preserve_lineage_and_structure() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"), (300.0, "Group")),
            ((40.0, "30 June 2026"), (300.0, "30 June 2025")),
            ((40.0, "Rs '000"), (300.0, "Rs '000")),
            ((40.0, "Profit for the period"), (300.0, "1,234"), (420.0, "2,000")),
            ((40.0, "Profit before tax"), (300.0, "(100)"), (420.0, "250")),
        )
    )
    statements = build_statements(document)
    assert len(statements) == 1
    statement = statements[0]
    assert len(statement.columns) == 2
    labels = [row.raw_label for row in statement.rows]
    assert "Profit for the period" in labels
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    assert pat.cells[0].parsed_numeric_value == Decimal("1234")
    assert pat.cells[0].source_ref.page_number == 1
    assert pat.cells[0].source_ref.bbox is not None
    assert pat.cells[0].source_ref.source_sha256 == document.source_sha256
    assert pat.cells[0].source_ref.raw_text == "1,234"
    pbt = next(row for row in statement.rows if "before tax" in row.raw_label.lower())
    assert pbt.cells[0].parsed_numeric_value == Decimal("-100")
    assert all(row.normalized_label for row in statement.rows)


def test_reconstruction_does_not_assign_metrics() -> None:
    document = geometric_document((((40.0, "Profit for the period"), (300.0, "10")),))
    statement = build_statements(document)[0]
    dumped = statement.model_dump()
    assert "metric_code" not in dumped
    assert all(column.entity_scope is None for column in statement.columns)


def test_parse_numeric_blank_dash_is_missing() -> None:
    assert parse_numeric("-") is None
    assert parse_numeric("0") == Decimal("0")


def test_packed_numeric_row_keeps_modal_column_count() -> None:
    document = geometric_document(
        (
            ((40.0, "Group Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            (
                (40.0, "Profit for the period"),
                (120.0, "100"),
                (150.0, "90"),
                (180.0, "80"),
                (210.0, "70"),
                (240.0, "60"),
                (270.0, "50"),
            ),
            (
                (40.0, "Revenue"),
                (120.0, "200"),
                (150.0, "190"),
                (180.0, "180"),
                (210.0, "170"),
                (240.0, "160"),
                (270.0, "150"),
            ),
        )
    )
    statement = build_statements(document)[0]
    assert len(statement.columns) == 6
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    assert [cell.parsed_numeric_value for cell in pat.cells] == [
        Decimal("100"),
        Decimal("90"),
        Decimal("80"),
        Decimal("70"),
        Decimal("60"),
        Decimal("50"),
    ]


def test_six_column_growth_row_keeps_all_value_cells() -> None:
    document = geometric_document(
        (
            ((80.0, "For the Six Months Ended"), (360.0, "For the Quarter Ended")),
            (
                (40.0, "Profit for the period"),
                (120.0, "6080157"),
                (200.0, "5488702"),
                (280.0, "10.78"),
                (360.0, "3174532"),
                (440.0, "2728017"),
                (520.0, "16.37"),
            ),
            (
                (40.0, "Interest income"),
                (120.0, "46942635"),
                (200.0, "39412000"),
                (280.0, "19.09"),
                (360.0, "24000000"),
                (440.0, "20000000"),
                (520.0, "21.12"),
            ),
        )
    )
    statement = build_statements(document)[0]
    assert len(statement.columns) == 6
    pat = next(row for row in statement.rows if row.raw_label == "Profit for the period")
    assert [cell.parsed_numeric_value for cell in pat.cells] == [
        Decimal("6080157"),
        Decimal("5488702"),
        Decimal("10.78"),
        Decimal("3174532"),
        Decimal("2728017"),
        Decimal("16.37"),
    ]


def test_docusign_envelope_line_is_header_not_a_row() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Docusign Envelope ID: 1D76594B-AAAA-BBBB-CCCC-DDDDEEEEFFFF"),),
            ((40.0, "Profit for the period"), (300.0, "7,694")),
        )
    )
    statement = build_statements(document)[0]
    assert all("Docusign" not in row.raw_label for row in statement.rows)
    assert len(statement.columns) == 1


def test_value_only_line_inherits_previous_account_label() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1000")),
            ((40.0, "Basic earnings per share"),),
            ((300.0, "1.46"), (420.0, "1.10")),
        )
    )
    statement = build_statements(document)[0]
    eps = next(row for row in statement.rows if "earnings per share" in row.raw_label.lower())
    assert [cell.parsed_numeric_value for cell in eps.cells] == [Decimal("1.46"), Decimal("1.10")]


def test_basic_diluted_child_rows_inherit_earnings_parent() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"), (220.0, "Group")),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "1000"), (340.0, "2000")),
            ((40.0, "Revenue"), (220.0, "5000"), (340.0, "6000")),
            ((40.0, "Gross profit"), (220.0, "3000"), (340.0, "4000")),
            ((40.0, "Operating profit"), (220.0, "1500"), (340.0, "2500")),
            ((40.0, "Profit before tax"), (220.0, "1200"), (340.0, "2200")),
            ((40.0, "Income tax"), (220.0, "200"), (340.0, "200")),
            ((40.0, "Profit after tax"), (220.0, "1000"), (340.0, "2000")),
            ((40.0, "Attributable to owners"), (220.0, "900"), (340.0, "1900")),
            ((40.0, "Non-controlling interest"), (220.0, "100"), (340.0, "100")),
            ((40.0, "Earnings per share"),),
            ((40.0, "- basic"), (220.0, "0.89"), (340.0, "1.10")),
            ((40.0, "- diluted"), (220.0, "0.89"), (340.0, "1.10")),
        )
    )
    statement = build_statements(document)[0]
    labels = [row.raw_label.lower() for row in statement.rows]
    assert any("basic" in label and "earnings per share" in label for label in labels)
    assert any("diluted" in label and "earnings per share" in label for label in labels)
    basic = next(row for row in statement.rows if "basic" in row.raw_label.lower())
    assert [cell.parsed_numeric_value for cell in basic.cells] == [Decimal("0.89"), Decimal("1.10")]


def test_rs_suffix_does_not_drop_basic_diluted_row() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"), (220.0, "Group")),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (220.0, "1000"), (340.0, "2000")),
            ((40.0, "Revenue"), (220.0, "5000"), (340.0, "6000")),
            ((40.0, "Gross profit"), (220.0, "3000"), (340.0, "4000")),
            ((40.0, "Operating profit"), (220.0, "1500"), (340.0, "2500")),
            ((40.0, "Profit before tax"), (220.0, "1200"), (340.0, "2200")),
            ((40.0, "Income tax"), (220.0, "200"), (340.0, "200")),
            ((40.0, "Profit after tax"), (220.0, "1000"), (340.0, "2000")),
            ((40.0, "Attributable to owners"), (220.0, "900"), (340.0, "1900")),
            ((40.0, "Non-controlling interest"), (220.0, "100"), (340.0, "100")),
            ((40.0, "Earnings per share"),),
            ((40.0, "Basic/Diluted (Rs.)"), (220.0, "2.48"), (340.0, "1.50")),
        )
    )
    statement = build_statements(document)[0]
    eps = next(row for row in statement.rows if "basic" in row.raw_label.lower())
    assert [cell.parsed_numeric_value for cell in eps.cells] == [Decimal("2.48"), Decimal("1.50")]


def test_eps_note_keeps_two_value_per_share_columns() -> None:
    document = geometric_document(
        (
            ((40.0, "30 June 2026"), (300.0, "30 June 2025")),
            ((40.0, "Last traded price"), (300.0, "238.00"), (420.0, "173.75")),
            ((40.0, "Net assets per share"), (300.0, "148.27"), (420.0, "127.14")),
            (
                (40.0, "No. of shares traded"),
                (120.0, "100"),
                (200.0, "90"),
                (300.0, "9894074"),
                (420.0, "8000000"),
                (500.0, "12"),
                (580.0, "8"),
            ),
        ),
        title="INVESTOR INFORMATION",
    )
    statement = build_statements(document)[0]
    navps = next(row for row in statement.rows if "net assets per share" in row.raw_label.lower())
    assert [cell.parsed_numeric_value for cell in navps.cells] == [
        Decimal("148.27"),
        Decimal("127.14"),
    ]
