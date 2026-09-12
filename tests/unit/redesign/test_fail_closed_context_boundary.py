from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from cse_financial_etl.contracts.eligibility import (
    ENTITY_UNKNOWN,
    PERIOD_UNKNOWN,
    ROLE_UNKNOWN,
    evaluate_eligibility,
)
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.recovery.entity_recovery import recover_entity
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.recovery.period_recovery import recover_period
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.tunnels.tunnel_a_geometry import _seed_layout_assist


def _ticket() -> FailureTicket:
    return FailureTicket("PAT:test", "PAT", "PERIOD_CONFLICT", "period", "test")


def _entry() -> LedgerEntry:
    return LedgerEntry(
        entry_id="e1",
        tunnel="A",
        concept="PAT",
        status="unresolved",
        raw_value=Decimal("10"),
        normalized_value=Decimal("10000"),
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
        evidence={"semantic_score": 1.0},
    )


def _default_evidence() -> dict[str, object]:
    return {
        "selected_line": "Profit for the period 10",
        "comparison_role": "CURRENT",
        "duration_months": 3,
        "entity_parent_kind": "COMPANY",
        "candidate_scores": [
            {
                "page": 1,
                "label": "Profit for the period",
                "raw_value": "10",
                "score": 0.95,
                "selected": True,
            }
        ],
        "graph": {
            "cluster_centers": [380.0, 485.0],
            "selected_score": 0.95,
        },
    }


def _layout_fact(**overrides: object) -> ExtractedFact:
    values: dict[str, object] = {
        "issuer_name": "Acme PLC",
        "symbol": "ACME.N0000",
        "period_end": date(2026, 6, 30),
        "metric_code": "PAT",
        "metric_type": "MONETARY_ABSOLUTE",
        "raw_text": "10",
        "raw_value": Decimal("10"),
        "normalized_value": Decimal("10000"),
        "currency": "LKR",
        "scale_factor": 1000,
        "entity_scope": "COMPANY",
        "source_page": 1,
        "source_line": "Profit for the period 10",
        "unit_source_text": "LKR '000",
        "confidence": "HIGH",
        "status": "EXTRACTED",
        "raw_label": "Profit for the period",
        "source_bbox": "{\"x0\":100,\"y0\":200,\"x1\":140,\"y1\":212}",
        "semantic_confidence": 1.0,
        "entity_confidence": 0.96,
        "period_confidence": 0.98,
        "unit_confidence": 1.0,
        "column_confidence": 0.95,
        "overall_certainty": 0.98,
        "comparison_role": "CURRENT",
        "duration_months": 3,
        "validation_status": "PASSED",
        "review_status": "REVIEW",
        "evidence_json": json.dumps(_default_evidence()),
    }
    values.update(overrides)
    return ExtractedFact(**values)  # type: ignore[arg-type]


def _seed_one(fact: ExtractedFact) -> LedgerEntry:
    ledger = CandidateLedger()
    _seed_layout_assist(ledger, [fact], tunnel="A")
    [entry] = ledger.entries
    return entry


def _assert_context_unresolved(entry: LedgerEntry) -> None:
    assert entry.entity is None
    assert entry.period_end is None
    assert entry.comparison_role is None
    assert entry.evidence["source_context_corroboration"]["bridge_eligible"] is False


def test_layout_source_corroboration_may_bridge_trusted_target_context() -> None:
    entry = _seed_one(_layout_fact())

    assert entry.entity == "COMPANY"
    assert entry.period_end == "2026-06-30"
    assert entry.comparison_role == "CURRENT"
    assert entry.evidence["context_not_source_owned"] is True
    corroboration = entry.evidence["source_context_corroboration"]
    assert corroboration["bridge_eligible"] is True
    assert corroboration["entity"] is True
    assert corroboration["target_period"] is True
    assert corroboration["column_identity"] is True
    assert corroboration["candidate_competition"] is True
    assert "layout_context_corroborated_by_pdf" in entry.reasons

    result = evaluate_eligibility(
        entry,
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert result.eligible
    assert result.reasons == ()


def test_layout_context_stays_unresolved_without_independent_pdf_corroboration() -> None:
    evidence = _default_evidence()
    evidence["comparison_role"] = "UNKNOWN"
    weak = _layout_fact(
        entity_confidence=0.72,
        period_confidence=0.80,
        comparison_role="UNKNOWN",
        evidence_json=json.dumps(evidence),
    )
    entry = _seed_one(weak)
    _assert_context_unresolved(entry)

    result = evaluate_eligibility(
        entry,
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert not result.eligible
    assert ENTITY_UNKNOWN in result.reasons
    assert PERIOD_UNKNOWN in result.reasons
    assert ROLE_UNKNOWN in result.reasons


def test_layout_context_stays_unresolved_without_geometry_reference() -> None:
    entry = _seed_one(_layout_fact(source_bbox=None))
    _assert_context_unresolved(entry)
    assert (
        entry.evidence["source_context_corroboration"]["has_geometry_reference"]
        is False
    )


def test_layout_context_stays_unresolved_without_column_identity() -> None:
    entry = _seed_one(_layout_fact(column_confidence=0.62))
    _assert_context_unresolved(entry)
    assert entry.evidence["source_context_corroboration"]["column_identity"] is False


def test_layout_context_stays_unresolved_for_near_tied_conflicting_rows() -> None:
    evidence = _default_evidence()
    evidence["candidate_scores"] = [
        {
            "page": 1,
            "label": "Profit for the period",
            "raw_value": "10",
            "score": 0.95,
            "selected": True,
        },
        {
            "page": 1,
            "label": "Profit for the period",
            "raw_value": "12",
            "score": 0.92,
            "selected": False,
        },
    ]
    entry = _seed_one(_layout_fact(evidence_json=json.dumps(evidence)))
    _assert_context_unresolved(entry)
    assert (
        entry.evidence["source_context_corroboration"]["candidate_competition"]
        is False
    )


def test_layout_context_stays_unresolved_for_ambiguous_dual_entity_structure() -> None:
    evidence = _default_evidence()
    evidence["graph"] = {
        "cluster_centers": [380.0, 485.0],
        "selected_score": 0.95,
    }
    entry = _seed_one(
        _layout_fact(
            entity_confidence=0.94,
            evidence_json=json.dumps(evidence),
        )
    )
    _assert_context_unresolved(entry)
    assert entry.evidence["source_context_corroboration"]["entity_structure"] is False


def test_layout_context_accepts_proven_dual_entity_structure() -> None:
    evidence = _default_evidence()
    evidence["graph"] = {
        "cluster_centers": [170.0, 270.0, 380.0, 485.0],
        "selected_score": 0.95,
    }
    entry = _seed_one(
        _layout_fact(
            entity_confidence=0.94,
            evidence_json=json.dumps(evidence),
        )
    )
    assert entry.entity == "COMPANY"
    assert entry.period_end == "2026-06-30"
    assert entry.comparison_role == "CURRENT"
    assert entry.evidence["source_context_corroboration"]["entity_structure"] is True


def test_entity_recovery_refuses_missing_target_scope() -> None:
    ledger = CandidateLedger([_entry()])
    result = recover_entity(_ticket(), ledger, context={})
    assert result == {"status": "SKIPPED", "reason": "missing_required_entity"}


def test_period_recovery_refuses_missing_target_duration() -> None:
    ledger = CandidateLedger([_entry()])
    result = recover_period(_ticket(), ledger, context={})
    assert result == {"status": "SKIPPED", "reason": "missing_target_duration"}
