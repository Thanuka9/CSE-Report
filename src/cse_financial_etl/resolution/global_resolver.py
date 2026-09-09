"""Global statement resolver — combines ledger + equations."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from cse_financial_etl.constraints.equation_registry import default_registry
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger
from cse_financial_etl.resolution.constraint_resolver import ResolverCResult, resolve_ambiguities
from cse_financial_etl.resolution.resource_budget import ResourceBudget


def global_resolve(
    ledger: CandidateLedger,
    *,
    required_entity: str,
    target_duration: int = 3,
    target_period_end: str | None = None,
    budget: ResourceBudget | None = None,
) -> tuple[CandidateLedger, ResolverCResult, list[Any]]:
    resolver = resolve_ambiguities(
        ledger,
        required_entity=required_entity,
        target_duration=target_duration,
        target_period_end=target_period_end,
        budget=budget,
    )
    values: dict[str, Decimal | None] = {}
    for entry in ledger.accepted():
        values[entry.concept] = entry.normalized_value
    equation_results = default_registry().evaluate(values, entity=required_entity, allow_derive=False)
    return ledger, resolver, equation_results
