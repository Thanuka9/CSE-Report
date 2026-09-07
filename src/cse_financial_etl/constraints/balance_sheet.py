"""Balance-sheet constraint helpers used by Resolver C."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.constraints.equation_registry import EquationResult, default_registry


def evaluate_balance_sheet(
    values: dict[str, Decimal | None],
    *,
    entity: str,
) -> list[EquationResult]:
    registry = default_registry()
    return [
        result
        for result in registry.evaluate(values, entity=entity)
        if result.equation_id.startswith("assets_")
    ]
