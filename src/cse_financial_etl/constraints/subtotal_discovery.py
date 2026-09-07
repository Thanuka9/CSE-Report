"""Subtotal hypotheses from hierarchy, indentation, and reconciliation (§21)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cse_financial_etl.compiler.canonical_statement import CanonicalFinancialStatement


@dataclass(frozen=True, slots=True)
class SubtotalHypothesis:
    row_id: str
    concept: str | None
    child_row_ids: tuple[str, ...]
    score: float
    evidence: str


def discover_subtotals(statement: CanonicalFinancialStatement) -> list[SubtotalHypothesis]:
    hyps: list[SubtotalHypothesis] = []
    for index, row in enumerate(statement.rows):
        if "total" not in row.normalized_label and "profit for" not in row.normalized_label:
            continue
        children = []
        for earlier in reversed(statement.rows[:index]):
            if earlier.indentation_level > row.indentation_level:
                children.append(earlier.row_id)
            elif earlier.indentation_level <= row.indentation_level and children:
                break
        score = 0.4 + (0.2 if children else 0.0)
        concept = row.hypotheses[0].concept if row.hypotheses else None
        hyps.append(
            SubtotalHypothesis(
                row_id=row.row_id,
                concept=concept,
                child_row_ids=tuple(reversed(children)),
                score=score,
                evidence="label_and_indent",
            )
        )
    return hyps


def printed_sum_matches(
    statement: CanonicalFinancialStatement,
    parent_row_id: str,
    child_row_ids: tuple[str, ...],
    column_id: str,
    *,
    tolerance: Decimal = Decimal("1"),
) -> bool:
    by_id = {r.row_id: r for r in statement.rows}
    parent = by_id.get(parent_row_id)
    if parent is None or column_id not in parent.cells:
        return False
    parent_val = parent.cells[column_id].normalized_value
    if parent_val is None:
        return False
    total = Decimal("0")
    for child_id in child_row_ids:
        child = by_id.get(child_id)
        if child is None or column_id not in child.cells:
            return False
        value = child.cells[column_id].normalized_value
        if value is None:
            return False
        total += value
    return abs(parent_val - total) <= tolerance
