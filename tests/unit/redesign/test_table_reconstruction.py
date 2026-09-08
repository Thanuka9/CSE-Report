"""Audit finding 1 — geometric column ownership in table reconstruction."""

from __future__ import annotations

from cse_financial_etl.document.table_reconstructor import reconstruct_page_tables

from .synthetic_pages import make_page, right_aligned, words

# Column right edges (points).
NOTE_X, C1_X, C2_X, C3_X, C4_X = 260.0, 340.0, 420.0, 500.0, 580.0


def _statement_page():
    return make_page(
        [
            words("COMPANY INCOME STATEMENT", 40),
            [*words("Company", 300)],
            [*words("For the three months ended 30 June", 300)],
            [("Note", 240, 260), ("2026", 318, 340), ("2025", 398, 420), ("2026", 478, 500), ("2025", 558, 580)],
            [("Rs.'000", 300, 340), ("Rs.'000", 380, 420), ("Rs.'000", 460, 500), ("Rs.'000", 540, 580)],
            [*words("Revenue", 40), right_aligned("4", NOTE_X), right_aligned("1,003,467", C1_X), right_aligned("965,141", C2_X), right_aligned("2,100", C3_X), right_aligned("2,000", C4_X)],
            # Blank intermediate column (C2) and no note number: C3/C4 must keep their columns.
            [*words("Other income", 40), right_aligned("120", C1_X), right_aligned("310", C3_X), right_aligned("290", C4_X)],
            [*words("Finance cost", 40), right_aligned("6", NOTE_X), right_aligned("(50)", C1_X), right_aligned("(45)", C2_X), right_aligned("-", C3_X), right_aligned("(10)", C4_X)],
            [*words("Profit before tax", 40), right_aligned("5,657,502", C1_X), right_aligned("1,394,110", C2_X), right_aligned("2,400", C3_X), right_aligned("2,300", C4_X)],
            [*words("Profit for the period", 40), right_aligned("5,378,093", C1_X), right_aligned("1,521,292", C2_X), right_aligned("2,200", C3_X), right_aligned("2,100", C4_X)],
        ]
    )


def _cells_by_row(table):
    out: dict[int, dict[int, str]] = {}
    for cell in table.cells:
        out.setdefault(cell.row_idx, {})[cell.col_idx] = cell.raw_text
    return out


def test_blank_intermediate_and_note_column_keep_neighbours_in_place() -> None:
    page = _statement_page()
    tables = reconstruct_page_tables(page)
    assert len(tables) == 1
    table = tables[0]
    kinds = {c.col_idx: c.kind for c in table.columns}
    assert kinds[0] == "LABEL"
    assert kinds[1] == "NOTE", kinds
    assert [kinds[i] for i in (2, 3, 4, 5)] == ["VALUE"] * 4

    rows = _cells_by_row(table)
    by_label = {cells[0]: cells for cells in rows.values()}
    revenue = by_label["Revenue"]
    assert revenue[1] == "4" and revenue[2] == "1,003,467" and revenue[5] == "2,000"
    other = by_label["Other income"]
    # No note, blank second value column: values must not shift left.
    assert 1 not in other and 3 not in other
    assert other[2] == "120" and other[4] == "310" and other[5] == "290"
    finance = by_label["Finance cost"]
    assert finance[4] == "-" and finance[5] == "(10)"
    pat = by_label["Profit for the period"]
    assert pat[2] == "5,378,093" and pat[3] == "1,521,292"


def test_every_numeric_cell_is_owned_by_a_column_interval() -> None:
    table = reconstruct_page_tables(_statement_page())[0]
    columns = {c.col_idx: c for c in table.columns}
    for cell in table.cells:
        if cell.col_idx == 0:
            continue
        col = columns[cell.col_idx]
        assert col.x_min <= cell.bbox.x1 <= col.x_max + 1e-6, (cell, col)


def test_header_region_and_title_are_preserved_separately_from_body() -> None:
    table = reconstruct_page_tables(_statement_page())[0]
    assert table.title_texts == ("COMPANY INCOME STATEMENT",)
    kinds = {p.kind for p in table.header_phrases}
    assert {"ENTITY", "DURATION", "YEAR", "UNIT", "NOTE"} <= kinds
    assert all(p.row_idx < min(c.row_idx for c in table.cells) for p in table.header_phrases)


def test_two_tables_on_one_page_stay_separate() -> None:
    page = make_page(
        [
            words("INCOME STATEMENT", 40),
            [("2026", 318, 340), ("2025", 398, 420)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("90", C2_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("9", C2_X)],
            words("STATEMENT OF FINANCIAL POSITION", 40),
            [*words("As at", 40), ("30.06.2026", 290, 340), ("31.03.2026", 370, 420)],
            [*words("Total assets", 40), right_aligned("500", C1_X), right_aligned("450", C2_X)],
            [*words("Total equity", 40), right_aligned("300", C1_X), right_aligned("280", C2_X)],
        ]
    )
    tables = reconstruct_page_tables(page)
    assert len(tables) == 2
    assert tables[0].title_texts == ("INCOME STATEMENT",)
    assert tables[1].title_texts == ("STATEMENT OF FINANCIAL POSITION",)
    first_labels = {c.raw_text for c in tables[0].cells if c.col_idx == 0}
    second_labels = {c.raw_text for c in tables[1].cells if c.col_idx == 0}
    assert "Revenue" in first_labels and "Total assets" not in first_labels
    assert "Total assets" in second_labels


def test_prose_with_embedded_numbers_is_not_a_body_row() -> None:
    page = make_page(
        [
            [("2026", 318, 340), ("2025", 398, 420)],
            [*words("Revenue", 40), right_aligned("100", C1_X), right_aligned("90", C2_X)],
            [*words("Profit for the period", 40), right_aligned("10", C1_X), right_aligned("9", C2_X)],
            words("Note : All values are in Rs '000s, unless otherwise stated.", 40),
            words("I certify that these statements comply with the Companies Act No. 07 of 2007", 40),
        ]
    )
    tables = reconstruct_page_tables(page)
    assert len(tables) == 1
    labels = [c.raw_text for c in tables[0].cells if c.col_idx == 0]
    assert labels == ["Revenue", "Profit for the period"]
    assert any("unless otherwise stated" in t for t in tables[0].footer_texts)
