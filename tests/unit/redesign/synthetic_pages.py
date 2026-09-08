"""Helpers to build synthetic PageIR fixtures for reconstruction / header tests."""

from __future__ import annotations

from cse_financial_etl.document.document_ir import BBox, LineIR, PageIR, TokenIR

# A token spec is (text, x0, x1); a line spec is a list of token specs.
TokenSpec = tuple[str, float, float]


def make_page(
    line_specs: list[list[TokenSpec]],
    *,
    width: float = 600.0,
    height: float = 840.0,
    y_start: float = 60.0,
    y_step: float = 14.0,
    page_number: int = 1,
) -> PageIR:
    lines: list[LineIR] = []
    all_tokens: list[TokenIR] = []
    for idx, spec in enumerate(line_specs):
        y0 = y_start + idx * y_step
        y1 = y0 + 10.0
        tokens = tuple(
            TokenIR(text=text, bbox=BBox(x0, y0, x1, y1), page_number=page_number) for text, x0, x1 in spec
        )
        if not tokens:
            continue
        all_tokens.extend(tokens)
        lines.append(
            LineIR(
                tokens=tokens,
                bbox=BBox(min(t.bbox.x0 for t in tokens), y0, max(t.bbox.x1 for t in tokens), y1),
                text=" ".join(t.text for t in tokens),
                page_number=page_number,
                line_id=f"p{page_number}-l{idx}",
            )
        )
    return PageIR(
        page_number=page_number,
        width=width,
        height=height,
        tokens=tuple(all_tokens),
        lines=tuple(lines),
    )


def right_aligned(text: str, right_edge: float, char_width: float = 5.5) -> TokenSpec:
    """A numeric token whose right edge sits on ``right_edge`` (column alignment)."""

    return (text, right_edge - len(text) * char_width, right_edge)


def words(text: str, x0: float, char_width: float = 5.0) -> list[TokenSpec]:
    """Split a label into word tokens laid out left-to-right from ``x0``."""

    specs: list[TokenSpec] = []
    cursor = x0
    for word in text.split():
        x1 = cursor + len(word) * char_width
        specs.append((word, cursor, x1))
        cursor = x1 + char_width
    return specs
