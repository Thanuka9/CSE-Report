from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.contracts.eligibility import (
    LABEL_EVIDENCE_WEAK,
    ROLE_UNKNOWN,
    evaluate_eligibility,
)
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.tunnels.tunnel_a_geometry import _seed_layout_assist


def _entry(**overrides: object) -> LedgerEntry:
    values: dict[str, object] = {
        "entry_id": "e1",
        "tunnel": "A",
        "concept": "PAT",
        "status": "accepted",
        "raw_value": Decimal("100"),
        "normalized_value": Decimal("100000"),
        "entity": "COMPANY",
        "period_end": "2026-06-30",
        "duration_months": 3,
        "comparison_role": "CURRENT",
        "unit": "LKR",
        "scale_factor": 1000,
        "page": 1,
        "bbox": None,
        "label": "Profit for the period",
        "score": 0.9,
        "evidence": {"semantic_score": 1.0},
    }
    values.update(overrides)
    return LedgerEntry(**values)  # type: ignore[arg-type]


def test_unknown_role_is_not_eligible_for_three_month_flow() -> None:
    result = evaluate_eligibility(
        _entry(comparison_role="UNKNOWN"),
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert not result.eligible
    assert ROLE_UNKNOWN in result.reasons


def test_unknown_role_is_allowed_for_exact_period_stock_fact() -> None:
    result = evaluate_eligibility(
        _entry(
            concept="TOTAL_ASSETS",
            duration_months=None,
            comparison_role="UNKNOWN",
            label="Total assets",
        ),
        required_entity="COMPANY",
        target_duration=None,
        target_period_end="2026-06-30",
        concept="TOTAL_ASSETS",
    )
    assert result.eligible
    assert ROLE_UNKNOWN not in result.reasons


def test_layout_assist_preserves_low_semantic_score_and_is_blocked() -> None:
    weak_pat = ExtractedFact(
        issuer_name="Lighthouse-shaped PLC",
        symbol="TEST.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Total Comprehensive Income/(Loss) for the Period 100",
        unit_source_text="Rs.'000",
        confidence="LOW",
        status="EXTRACTED",
        raw_label="Total Comprehensive Income/(Loss) for the Period",
        extraction_method="LAYOUT_TEXT",
        semantic_model="rapidfuzz-token-set",
        semantic_confidence=0.1,
        overall_certainty=0.4,
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
    )
    ledger = CandidateLedger()
    _seed_layout_assist(ledger, [weak_pat], tunnel="A")

    [entry] = ledger.entries
    assert entry.evidence["semantic_score"] == 0.1
    assert entry.evidence["semantic_model"] == "rapidfuzz-token-set"

    result = evaluate_eligibility(
        entry,
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert not result.eligible
    assert LABEL_EVIDENCE_WEAK in result.reasons
