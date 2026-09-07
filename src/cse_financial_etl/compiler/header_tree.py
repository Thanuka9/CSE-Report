"""Simplify multi-row header tree compilation (§11)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from cse_financial_etl.document.document_ir import TableIR


@dataclass(frozen=True, slots=True)
class HeaderNode:
    text: str
    entity: str | None = None
    comparison_role: str | None = None
    duration_months: int | None = None
    period_end: date | None = None
    children: tuple[HeaderNode, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledHeaderColumn:
    column_id: str
    entity: str | None
    comparison_role: str | None
    duration_months: int | None
    period_end: date | None
    path: tuple[str, ...]


_ENTITY_RE = re.compile(r"\b(group|company|bank|consolidated|separate)\b", re.I)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def compile_header_tree(table: TableIR, header_texts: list[str]) -> list[CompiledHeaderColumn]:
    """Compile multi-row headers into explicit semantic columns."""

    blob = " | ".join(header_texts)
    entities = [_normalize_entity(e) for e in _ENTITY_RE.findall(blob)]
    # Preserve order, unique.
    ordered_entities: list[str] = []
    for entity in entities:
        if entity not in ordered_entities:
            ordered_entities.append(entity)
    if not ordered_entities:
        ordered_entities = ["COMPANY"]
    durations = _parse_durations(blob)
    years = [int(y) for y in _YEAR_RE.findall(blob)]
    col_indices = sorted({c.col_idx for c in table.cells if c.col_idx > 0}) or [1]
    columns: list[CompiledHeaderColumn] = []
    for offset, col_idx in enumerate(col_indices):
        if len(ordered_entities) == 1:
            entity = ordered_entities[0]
        else:
            mid = (col_indices[0] + col_indices[-1]) / 2.0
            # Left block → first named entity, right → second (handles Company|Group reverse).
            entity = ordered_entities[0] if col_idx <= mid else ordered_entities[1]
        role = "CURRENT" if offset % 2 == 0 else "COMPARATIVE"
        duration = durations[offset % len(durations)] if durations else None
        period = date(years[offset % len(years)], 12, 31) if years else None
        columns.append(
            CompiledHeaderColumn(
                column_id=f"c{col_idx}",
                entity=entity,
                comparison_role=role,
                duration_months=duration,
                period_end=period,
                path=tuple(header_texts[:3]),
            )
        )
    return columns


def _normalize_entity(raw: str) -> str:
    lower = raw.lower()
    if lower in {"group", "consolidated"}:
        return "GROUP"
    if lower == "bank":
        return "BANK"
    return "COMPANY"


def _parse_durations(blob: str) -> list[int]:
    found: list[int] = []
    lower = blob.lower()
    patterns = (
        (r"three months|3 months|\bquarter\b", 3),
        (r"six months|6 months", 6),
        (r"nine months|9 months", 9),
        (r"twelve months|12 months|year ended|\bfy\b", 12),
    )
    for pattern, months in patterns:
        if re.search(pattern, lower):
            found.append(months)
    return found or [3]
