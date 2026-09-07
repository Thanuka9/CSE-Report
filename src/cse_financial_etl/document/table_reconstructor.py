"""Reconstruct table structure from visual rows and numeric column clusters."""

from __future__ import annotations

from cse_financial_etl.document.document_ir import (
    BBox,
    CanonicalDocumentIR,
    LineIR,
    PageIR,
    TableCellIR,
    TableIR,
)
from cse_financial_etl.document.geometry import line_label_and_numerics
from cse_financial_etl.documents.document_ir import cluster_numeric_columns


def reconstruct_tables(document: CanonicalDocumentIR) -> CanonicalDocumentIR:
    """Attach TableIR objects to each page (header rows + body cells)."""

    pages: list[PageIR] = []
    for page in document.pages:
        tables = tuple(_tables_for_page(page))
        pages.append(
            PageIR(
                page_number=page.page_number,
                width=page.width,
                height=page.height,
                tokens=page.tokens,
                lines=page.lines,
                tables=tables,
            )
        )
    return CanonicalDocumentIR(
        pages=tuple(pages),
        quality=document.quality,
        source_sha256=document.source_sha256,
        source_path=document.source_path,
    )


def _tables_for_page(page: PageIR) -> list[TableIR]:
    if not page.lines:
        return []

    class _Tok:
        __slots__ = ("bbox", "is_numeric", "text")

        def __init__(self, text: str, bbox: BBox, is_numeric: bool) -> None:
            self.text = text
            self.bbox = bbox
            self.is_numeric = is_numeric

    class _LegacyLine:
        def __init__(self, line: LineIR) -> None:
            self.tokens = [
                _Tok(t.text, t.bbox, _num(t.text)) for t in line.tokens
            ]

    legacy_lines = [_LegacyLine(line) for line in page.lines]
    centres = cluster_numeric_columns(legacy_lines)  # type: ignore[arg-type]
    if not centres:
        return []
    cells: list[TableCellIR] = []
    header_rows: list[int] = []
    for row_idx, line in enumerate(page.lines):
        label, numerics = line_label_and_numerics(line)
        if label and not numerics and row_idx < 6:
            header_rows.append(row_idx)
        cells.append(
            TableCellIR(row_idx=row_idx, col_idx=0, raw_text=label, bbox=line.bbox)
        )
        for col_idx, token in enumerate(numerics, start=1):
            cells.append(
                TableCellIR(
                    row_idx=row_idx,
                    col_idx=col_idx,
                    raw_text=token.text,
                    bbox=token.bbox,
                )
            )
    if not cells:
        return []
    return [
        TableIR(
            page_number=page.page_number,
            bbox=BBox(0, 0, page.width, page.height),
            cells=tuple(cells),
            header_rows=tuple(header_rows),
            source_method="geometry_cluster",
        )
    ]


def _num(text: str) -> bool:
    cleaned = text.replace(" ", "").replace(",", "")
    if cleaned in {"-", "–", "—"}:
        return True
    try:
        float(cleaned.strip("()%"))
        return True
    except ValueError:
        return False
