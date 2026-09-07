"""Publication gates adapter — redesign no-overpublication checks (§47.10)."""

from __future__ import annotations

from typing import Any

from cse_financial_etl.validation.final_validator import gate_no_overpublication


def evaluate_publication_gates(
    *,
    queried_facts: list[Any] | None = None,
    ratios: list[Any] | None = None,
) -> dict[str, Any]:
    """Return redesign publication gate outcomes (compose with production_gates separately)."""

    redesign_violations = gate_no_overpublication(queried_facts or [], ratios or [])
    return {
        "redesign_violations": redesign_violations,
        "ok": not redesign_violations,
    }
