"""Profit & loss constraint helpers."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.constraints.equation_registry import EquationResult, default_registry


def evaluate_profit_loss(
    values: dict[str, Decimal | None],
    *,
    entity: str,
    allow_derive: bool = False,
) -> list[EquationResult]:
    registry = default_registry()
    return [
        result
        for result in registry.evaluate(values, entity=entity, allow_derive=allow_derive)
        if result.equation_id.startswith("pat_")
    ]
