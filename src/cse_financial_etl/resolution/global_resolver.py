"""Global statement resolver — combines ledger + equations."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.constraints.equation_registry import default_registry
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger
from cse_financial_etl.resolution.constraint_resolver import ResolverCResult, resolve_ambiguities


def global_resolve(
    ledger: CandidateLedger,
    *,
    required_entity: str,
    target_duration: int = 3,
) -> tuple[CandidateLedger, ResolverCResult, list]:
    resolver = resolve_ambiguities(
        ledger,
        required_entity=required_entity,
        target_duration=target_duration,
    )
    values: dict[str, Decimal | None] = {}
    for entry in ledger.accepted():
        values[entry.concept] = entry.normalized_value
    equation_results = default_registry().evaluate(values, entity=required_entity, allow_derive=False)
    return ledger, resolver, equation_results
