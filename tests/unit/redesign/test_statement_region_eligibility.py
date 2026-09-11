from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.contracts.eligibility import (
    STATEMENT_REGION_UNKNOWN,
    STATEMENT_REGION_WEAK,
    evaluate_eligibility,
)
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry


def _entry(region_confidence: object = 0.9) -> LedgerEntry:
    evidence = {
        "candidate_origin": "compiler_geometry",
        "semantic_score": 1.0,
        "statement_region_confidence": region_confidence,
    }
    return LedgerEntry(
        entry_id="e1",
        tunnel="A",
        concept="PAT",
        status="unresolved",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        entity="COMPANY",
        period_end="2026-06-30",
        duration_months=3,
        comparison_role="CURRENT",
        unit="LKR",
        scale_factor=1000,
        page=1,
        bbox=None,
        label="Profit for the period",
        score=1.0,
        evidence=evidence,
    )


def test_numeric_density_region_cannot_independently_publish() -> None:
    result = evaluate_eligibility(
        _entry(0.45),
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert not result.eligible
    assert STATEMENT_REGION_WEAK in result.reasons


def test_native_candidate_requires_region_provenance() -> None:
    entry = _entry()
    entry.evidence.pop("statement_region_confidence")
    result = evaluate_eligibility(
        entry,
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert not result.eligible
    assert STATEMENT_REGION_UNKNOWN in result.reasons


def test_heading_backed_region_remains_eligible() -> None:
    result = evaluate_eligibility(
        _entry(0.9),
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert result.eligible
