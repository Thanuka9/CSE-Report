from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.resolution.constraint_resolver import resolve_ambiguities
from cse_financial_etl.resolution.resource_budget import ResourceBudget

PERIOD = "2026-06-30"


def _candidate(concept: str, suffix: str, score: float) -> LedgerEntry:
    return LedgerEntry(
        entry_id=f"{concept}-{suffix}",
        tunnel="A",
        concept=concept,
        status="unresolved",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        entity="BANK",
        period_end=PERIOD,
        duration_months=None,
        comparison_role="CURRENT",
        unit="LKR",
        scale_factor=1000,
        page=1,
        bbox="0,0,1,1",
        label=concept.replace("_", " ").title(),
        score=score,
        evidence={"semantic_score": 1.0},
    )


def test_iteration_budget_is_applied_per_concept_not_shared() -> None:
    ledger = CandidateLedger(
        [
            _candidate("TOTAL_ASSETS", "winner", 0.9),
            _candidate("TOTAL_ASSETS", "runner", 0.6),
            _candidate("TOTAL_LIABILITIES", "winner", 0.9),
            _candidate("TOTAL_LIABILITIES", "runner", 0.6),
        ]
    )
    result = resolve_ambiguities(
        ledger,
        required_entity="BANK",
        target_period_end=PERIOD,
        budget=ResourceBudget(max_iterations=2, max_elapsed_seconds=10),
    )

    assert result.by_concept["TOTAL_ASSETS"].status == "RESOLVED"
    assert result.by_concept["TOTAL_LIABILITIES"].status == "RESOLVED"
    assert result.by_concept["TOTAL_ASSETS"].winner is not None
    assert result.by_concept["TOTAL_LIABILITIES"].winner is not None
    budget_report = result.report["resource_budget"]
    assert budget_report["max_iterations_scope"] == "PER_CONCEPT"
    assert budget_report["total_iterations_used"] == 4
    assert budget_report["per_concept"]["TOTAL_ASSETS"]["iterations_used"] == 2
    assert budget_report["per_concept"]["TOTAL_LIABILITIES"]["iterations_used"] == 2


def test_global_hypothesis_budget_still_fails_closed() -> None:
    ledger = CandidateLedger(
        [
            _candidate("TOTAL_ASSETS", "winner", 0.9),
            _candidate("TOTAL_ASSETS", "runner", 0.6),
            _candidate("TOTAL_LIABILITIES", "winner", 0.9),
            _candidate("TOTAL_LIABILITIES", "runner", 0.6),
        ]
    )
    result = resolve_ambiguities(
        ledger,
        required_entity="BANK",
        target_period_end=PERIOD,
        budget=ResourceBudget(max_hypotheses=3, max_elapsed_seconds=10),
    )

    assert {row.status for row in result.by_concept.values()} == {
        "SEARCH_BUDGET_EXHAUSTED"
    }
    assert result.report["resource_budget"]["stop_reason"] == (
        "HYPOTHESIS_BUDGET_EXHAUSTED"
    )
