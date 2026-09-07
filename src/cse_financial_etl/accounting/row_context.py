"""Row-sequence / structural semantics — never interpret rows in isolation (§18)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RowContext:
    row_id: str
    label: str
    previous_labels: tuple[str, ...]
    next_labels: tuple[str, ...]
    parent_section: str | None
    indentation_level: int
    position: int
    is_subtotal_like: bool


def build_row_context(
    rows: list[tuple[str, str, int]],
    index: int,
    *,
    window: int = 3,
) -> RowContext:
    """rows: list of (row_id, label, indentation)."""

    row_id, label, indent = rows[index]
    prev = tuple(r[1] for r in rows[max(0, index - window) : index])
    nxt = tuple(r[1] for r in rows[index + 1 : index + 1 + window])
    parent = None
    for earlier in reversed(rows[:index]):
        if earlier[2] < indent:
            parent = earlier[1]
            break
    subtotal_like = any(
        key in label.lower()
        for key in ("total", "profit for", "profit after", "sub total", "subtotal")
    )
    return RowContext(
        row_id=row_id,
        label=label,
        previous_labels=prev,
        next_labels=nxt,
        parent_section=parent,
        indentation_level=indent,
        position=index,
        is_subtotal_like=subtotal_like,
    )


def structural_boost(context: RowContext, concept: str) -> float:
    boost = 0.0
    if context.is_subtotal_like and concept in {
        "PAT",
        "TOTAL_ASSETS",
        "TOTAL_EQUITY",
        "TOTAL_LIABILITIES",
        "OPERATING_PROFIT",
        "PBT",
    }:
        boost += 0.15
    if (
        context.parent_section
        and "equity" in context.parent_section.lower()
        and concept in {"TOTAL_EQUITY", "SHARE_CAPITAL", "RESERVES", "NCI_EQUITY"}
    ):
        boost += 0.1
    if any("tax" in p.lower() for p in context.previous_labels) and concept == "PAT":
        boost += 0.1
    return min(boost, 0.4)
