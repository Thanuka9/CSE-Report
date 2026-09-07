"""Final validation and publication gates for the compiler path (§41, §49)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cse_financial_etl.accounting.concept_rules import (
    group_cannot_satisfy_company,
    requires_exact_3m,
)
from cse_financial_etl.facts.derived_facts import DerivedRatio
from cse_financial_etl.facts.query_engine import QueriedFact
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry


@dataclass(frozen=True, slots=True)
class FinalCheck:
    metric_code: str
    status: str  # PASS | FAIL | UNTESTED | NOT_APPLICABLE
    detail: str


def validate_source_fact(entry: LedgerEntry | None, *, required_entity: str, target_duration: int) -> FinalCheck:
    if entry is None:
        return FinalCheck("UNKNOWN", "UNTESTED", "no_entry")
    if group_cannot_satisfy_company(required_entity, entry.entity or ""):
        return FinalCheck(entry.concept, "FAIL", "group_cannot_satisfy_company")
    if (
        requires_exact_3m(entry.concept)
        and entry.duration_months not in {None, target_duration}
        and entry.duration_months
        and entry.duration_months != target_duration
    ):
        return FinalCheck(entry.concept, "FAIL", "ytd_cannot_satisfy_3m")
    if entry.comparison_role == "COMPARATIVE":
        return FinalCheck(entry.concept, "FAIL", "comparative_not_current")
    if entry.normalized_value is None:
        return FinalCheck(entry.concept, "UNTESTED", "missing_value")
    return FinalCheck(entry.concept, "PASS", "source_context_ok")


def publication_allowed(
    fact: QueriedFact,
    check: FinalCheck,
    *,
    review_required: bool = True,
) -> bool:
    """No confidence threshold directly publishes. Source facts need review gate."""

    if fact.status != "EXTRACTED":
        return False
    if check.status == "FAIL":
        return False
    if fact.entry is None or fact.entry.normalized_value is None:
        return False
    # Derived-looking liabilities from Assets-Equity are never publishable as source.
    if fact.concept == "TOTAL_LIABILITIES":
        reasons = " ".join(fact.entry.reasons).upper()
        if "ASSETS" in reasons and "EQUITY" in reasons and "DERIV" in reasons:
            return False
    return not review_required


def gate_no_overpublication(facts: list[QueriedFact], ratios: list[DerivedRatio]) -> list[str]:
    """§47.10 no-overpublication checks."""

    violations: list[str] = []
    for fact in facts:
        if fact.entry is None:
            continue
        if fact.status == "EXTRACTED" and fact.entry.entity == "GROUP" and fact.concept in {
            "PAT",
            "PBT",
            "TOP_LINE",
            "OPERATING_PROFIT",
            "TOTAL_ASSETS",
            "TOTAL_EQUITY",
            "TOTAL_LIABILITIES",
        }:
            # Caller must have required COMPANY/BANK — flag if Group slipped through.
            violations.append(f"GROUP_SUBSTITUTION:{fact.concept}")
        if (
            fact.status == "EXTRACTED"
            and requires_exact_3m(fact.concept)
            and fact.entry.duration_months
            and fact.entry.duration_months != 3
        ):
            violations.append(f"YTD_AS_QUARTER:{fact.concept}")
        if fact.status == "EXTRACTED" and fact.entry.comparison_role == "COMPARATIVE":
            violations.append(f"COMPARATIVE_AS_CURRENT:{fact.concept}")
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
