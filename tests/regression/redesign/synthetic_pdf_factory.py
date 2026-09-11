"""Deterministic PDF fixtures for end-to-end extraction regression tests.

The fixtures are generated at test time with PyMuPDF so they exercise the exact same
PDF -> coordinate IR -> region/table compiler -> resolver -> publisher path as real
filings without committing opaque binary test data.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pymupdf as fitz

TextOp = tuple[float, float, str]
ValueCell = tuple[float, str]
RowSpec = tuple[str, Sequence[ValueCell]]

PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0


def statement_page(
    *,
    title: str,
    period_line: str,
    unit_line: str | None,
    headers: Sequence[ValueCell],
    rows: Sequence[RowSpec],
    title_x: float = 48.0,
    label_x: float = 48.0,
    extra_top_lines: Iterable[str] = (),
    extra_bottom_lines: Iterable[str] = (),
) -> list[TextOp]:
    """Build a simple coordinate-owned financial statement page.

    Values are positioned explicitly rather than written as a text blob. This is
    important because the production parser is expected to reason from geometry,
    not the PDF's internal text ordering.
    """

    ops: list[TextOp] = [(title_x, 48.0, title)]
    y = 66.0
    for line in extra_top_lines:
        ops.append((title_x, y, line))
        y += 14.0
    ops.append((title_x, y, period_line))
    y += 16.0
    if unit_line:
        ops.append((title_x, y, unit_line))
        y += 18.0
    for x, text in headers:
        ops.append((x, y, text))
    y += 20.0
    for label, values in rows:
        ops.append((label_x, y, label))
        for x, text in values:
            ops.append((x, y, text))
        y += 18.0
    y += 10.0
    for line in extra_bottom_lines:
        ops.append((title_x, y, line))
        y += 14.0
    return ops


def write_pdf(path: Path, pages: Sequence[Sequence[TextOp]]) -> Path:
    """Write a deterministic, searchable PDF from positioned text operations."""

    path.parent.mkdir(parents=True, exist_ok=True)
    document = fitz.open()  # type: ignore[no-untyped-call]
    try:
        for page_ops in pages:
            page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            for x, y, text in page_ops:
                page.insert_text((x, y), str(text), fontname="helv", fontsize=9.0)
        document.save(path, garbage=4, deflate=True)
    finally:
        document.close()
    return path
