"""Route unresolved dimensions to materially different recovery methods (§33)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cse_financial_etl.recovery.entity_recovery import recover_entity
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.recovery.numeric_recovery import recover_numeric
from cse_financial_etl.recovery.ocr_recovery import recover_ocr
from cse_financial_etl.recovery.period_recovery import recover_period
from cse_financial_etl.recovery.semantic_recovery import recover_semantic
from cse_financial_etl.recovery.structural_recovery import recover_structural
from cse_financial_etl.recovery.unit_recovery import recover_unit
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger

_ROUTES: dict[str, Callable[..., dict[str, Any]]] = {
    "structural_recovery": recover_structural,
    "semantic_recovery": recover_semantic,
    "unit_recovery": recover_unit,
    "numeric_recovery": recover_numeric,
    "entity_recovery": recover_entity,
    "period_recovery": recover_period,
    "ocr_recovery": recover_ocr,
}


def run_recovery(
    tickets: list[FailureTicket],
    ledger: CandidateLedger,
    *,
    context: dict[str, Any] | None = None,
) -> list[FailureTicket]:
    ctx = context or {}
    for ticket in tickets:
        for route_name in ticket.recovery_routes:
            route = _ROUTES.get(route_name)
            if route is None:
                ticket.attempts.append({"route": route_name, "status": "SKIPPED", "reason": "unknown_route"})
                continue
            outcome = route(ticket, ledger, context=ctx)
            ticket.attempts.append({"route": route_name, **outcome})
            if outcome.get("status") == "RECOVERED":
                ticket.terminal_status = "RECOVERED"
                break
        if ticket.terminal_status is None:
            if any(a.get("status") == "SKIPPED" for a in ticket.attempts):
                ticket.terminal_status = "SEARCH_INCOMPLETE"
            else:
                ticket.terminal_status = "NOT_LOCATED_AFTER_CONFIGURED_RECOVERY"
    return tickets
