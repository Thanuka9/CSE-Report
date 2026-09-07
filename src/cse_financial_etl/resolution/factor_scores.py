"""Deterministic weighted factor scores for eligible candidates (§30)."""

from __future__ import annotations

from cse_financial_etl.resolution.candidate_ledger import LedgerEntry


def score_factors(entry: LedgerEntry, *, required_entity: str, target_duration: int) -> float:
    score = entry.score
    if entry.entity == required_entity:
        score += 0.25
    elif entry.entity == "GROUP" and required_entity in {"COMPANY", "BANK"}:
        score -= 1.0  # hard ineligibility reflected as crushing penalty
    if entry.duration_months == target_duration:
        score += 0.25
    elif entry.duration_months and entry.duration_months != target_duration:
        score -= 0.8
    if entry.comparison_role == "CURRENT":
        score += 0.15
    elif entry.comparison_role == "COMPARATIVE":
        score -= 0.5
    return score
