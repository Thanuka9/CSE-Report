"""Final validation and publication gates for the compiler path (§41, §49).

The final validator re-runs the shared eligibility contract on the *chosen*
evidence, independently of the arbiter that selected it, and adds the
no-overpublication checks. A FAIL here is preserved on the published fact until
an explicit revalidation produces a new result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cse_financial_etl.accounting.concept_rules import requires_exact_3m
from cse_financial_etl.contracts.eligibility import FinalCheck, evaluate_eligibility
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry

if TYPE_CHECKING:  # dependency-neutral at runtime: facts imports *this* module
    from cse_financial_etl.facts.derived_facts import DerivedRatio
    from cse_financial_etl.facts.query_engine import QueriedFact

__all__ = [
    "FinalCheck",
    "build_extraction_report",
    "gate_no_overpublication",
    "publication_allowed",
    "validate_source_fact",
]


def validate_source_fact(
    entry: LedgerEntry | None,
    *,
    required_entity: str,
    target_duration: int,
    target_period_end: str | None = None,
    concept: str | None = None,
) -> FinalCheck:
    """Independent re-check of the selected evidence against the shared contract."""

    if entry is None:
        return FinalCheck(concept or "UNKNOWN", "UNTESTED", "no_entry")
    result = evaluate_eligibility(
        entry,
        required_entity=required_entity,
        target_duration=target_duration if requires_exact_3m(concept or entry.concept) else None,
        target_period_end=target_period_end,
        concept=concept,
    )
    if result.eligible:
        return FinalCheck(entry.concept, "PASS", "source_context_ok")
    return FinalCheck(entry.concept, "FAIL", ",".join(result.reasons), result.reasons)


def publication_allowed(
    fact: QueriedFact,
    check: FinalCheck,
    *,
    review_required: bool = True,
) -> bool:
    """Machine eligibility only. Official release additionally needs a reviewer approval
    bound to the fact identity (see :mod:`cse_financial_etl.contracts.release`)."""

    if fact.status != "EXTRACTED":
        return False
    if check.status != "PASS":
        return False
    if fact.entry is None or fact.entry.normalized_value is None:
        return False
    return not review_required


def gate_no_overpublication(facts: list[QueriedFact], ratios: list[DerivedRatio]) -> list[str]:
    """§47.10 no-overpublication checks."""

    violations: list[str] = []
    for fact in facts:
        if fact.entry is None or fact.status != "EXTRACTED":
            continue
        if fact.entry.entity == "GROUP" and fact.metric_code in {
            "PAT",
            "PBT",
            "TOP_LINE",
            "OPERATING_PROFIT",
            "TOTAL_ASSETS",
            "TOTAL_EQUITY",
            "TOTAL_LIABILITIES",
        }:
            violations.append(f"GROUP_SUBSTITUTION:{fact.metric_code}")
        if requires_exact_3m(fact.concept) and fact.entry.duration_months != 3:
            violations.append(f"YTD_AS_QUARTER:{fact.metric_code}")
        if fact.entry.comparison_role != "CURRENT":
            violations.append(f"COMPARATIVE_AS_CURRENT:{fact.metric_code}")
        if not fact.entry.unit and fact.concept not in {"WEIGHTED_AVG_SHARES", "ORDINARY_SHARES"}:
            violations.append(f"UNIT_MISSING:{fact.metric_code}")
    for ratio in ratios:
        if ratio.status == "EXTRACTED_DERIVED" and ratio.value is None:
            violations.append(f"BLANK_RATIO:{ratio.code}")
    return violations


def build_extraction_report(
    *,
    filing_sha: str,
    known: dict[str, Any],
    document_quality: dict[str, Any],
    statements_detected: list[Any],
    tunnel_a: dict[str, Any],
    tunnel_b: dict[str, Any] | None,
    resolver_c: dict[str, Any],
    arbiter: list[Any],
    failure_tickets: list[Any],
    recovery_attempts: list[Any],
    final_facts: list[Any],
    terminal_unresolved: list[Any],
) -> dict[str, Any]:
    """Production logging contract (§50)."""

    return {
        "filing_sha": filing_sha,
        "known_context": known,
        "document_quality": document_quality,
        "statements_detected": statements_detected,
        "tunnel_a": tunnel_a,
        "tunnel_b": tunnel_b or {},
        "resolver_c": resolver_c,
        "arbiter": arbiter,
        "failure_tickets": failure_tickets,
        "recovery_attempts": recovery_attempts,
        "final_facts": final_facts,
        "terminal_unresolved": terminal_unresolved,
    }
