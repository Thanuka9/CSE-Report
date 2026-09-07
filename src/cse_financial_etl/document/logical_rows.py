"""Logical row reconstruction: merge split labels and detached unit lines."""

from __future__ import annotations

from dataclasses import dataclass

from cse_financial_etl.document.document_ir import LineIR, PageIR
from cse_financial_etl.document.geometry import line_label_and_numerics


@dataclass(frozen=True, slots=True)
class LogicalRow:
    page_number: int
    raw_label: str
    normalized_label: str
    source_lines: tuple[LineIR, ...]
    indentation_level: int


def build_logical_rows(page: PageIR) -> list[LogicalRow]:
    rows: list[LogicalRow] = []
    index = 0
    lines = list(page.lines)
    while index < len(lines):
        line = lines[index]
        label, numerics = line_label_and_numerics(line)
        merged = [line]
        while index + 1 < len(lines) and not numerics:
            nxt = lines[index + 1]
            n_label, n_nums = line_label_and_numerics(nxt)
            if n_nums and (not n_label or n_label.lower() in {"rs.", "rs", "lkr"}):
                merged.append(nxt)
                numerics = n_nums
                label = f"{label} {n_label}".strip()
                index += 1
                break
            if n_label and not n_nums and abs(nxt.bbox.y0 - line.bbox.y1) < 14:
                merged.append(nxt)
                label = f"{label} {n_label}".strip()
                index += 1
                line = nxt
                continue
            break
        indent = max(0, int(merged[0].bbox.x0 // 12))
        rows.append(
            LogicalRow(
                page_number=page.page_number,
                raw_label=label,
                normalized_label=_normalize_label(label),
                source_lines=tuple(merged),
                indentation_level=indent,
            )
        )
        index += 1
    return rows


def _normalize_label(label: str) -> str:
    return " ".join(label.lower().replace("'", "").split())
