"""Cross-column consistency checks (§22)."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.compiler.canonical_statement import CanonicalFinancialStatement


def cross_column_equation_agreement(
    statement: CanonicalFinancialStatement,
    concept: str,
    *,
    equation: str = "identity",
) -> dict[str, str]:
    """Return per-column support status for a concept appearing in multiple columns."""

    statuses: dict[str, str] = {}
    for column in statement.columns:
        found = None
        for row in statement.rows:
            if any(h.concept == concept for h in row.hypotheses) and column.column_id in row.cells:
                found = row.cells[column.column_id].normalized_value
                break
        statuses[column.column_id] = "PRESENT" if found is not None else "ABSENT"
    return statuses


def values_agree(
    left: Decimal | None,
    right: Decimal | None,
    *,
    tolerance: Decimal = Decimal("1"),
) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= tolerance
