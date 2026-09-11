from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.recovery.entity_recovery import recover_entity
from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.recovery.period_recovery import recover_period
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.tunnels.tunnel_a_geometry import _seed_layout_assist
from cse_financial_etl.contracts.eligibility import ENTITY_UNKNOWN, PERIOD_UNKNOWN, ROLE_UNKNOWN, evaluate_eligibility


def _ticket() -> FailureTicket:
    return FailureTicket("PAT:test", "PAT", "PERIOD_CONFLICT", "period", "test")


def _entry() -> LedgerEntry:
    return LedgerEntry(
        entry_id="e1", tunnel="A", concept="PAT", status="unresolved",
        raw_value=Decimal("10"), normalized_value=Decimal("10000"),
        entity="COMPANY", period_end="2026-06-30", duration_months=3,
        comparison_role="CURRENT", unit="LKR", scale_factor=1000,
        page=1, bbox=None, label="Profit for the period", score=1.0,
        evidence={"semantic_score": 1.0},
    )


def test_layout_target_context_is_never_laundered_into_source_evidence() -> None:
    fact = ExtractedFact(
        issuer_name="Acme PLC", symbol="ACME.N0000", period_end=date(2026, 6, 30),
        metric_code="PAT", metric_type="MONETARY_ABSOLUTE", raw_text="10",
        raw_value=Decimal("10"), normalized_value=Decimal("10000"), currency="LKR",
        scale_factor=1000, entity_scope="COMPANY", source_page=1,
        source_line="Profit for the period 10", unit_source_text="LKR '000",
        confidence="HIGH", status="EXTRACTED", semantic_confidence=1.0,
        entity_confidence=1.0, period_confidence=1.0, unit_confidence=1.0,
        column_confidence=1.0, overall_certainty=1.0,
        comparison_role="CURRENT", duration_months=3, validation_status="PASSED",
        review_status="REVIEW",
    )
    ledger = CandidateLedger()
    _seed_layout_assist(ledger, [fact], tunnel="A")
    [entry] = ledger.entries
    assert entry.entity is None
    assert entry.period_end is None
    assert entry.comparison_role is None
    assert entry.evidence["legacy_target_period"] == "2026-06-30"
    result = evaluate_eligibility(
        entry, required_entity="COMPANY", target_duration=3,
        target_period_end="2026-06-30", concept="PAT"
    )
    assert not result.eligible
    assert ENTITY_UNKNOWN in result.reasons
    assert PERIOD_UNKNOWN in result.reasons
    assert ROLE_UNKNOWN in result.reasons


def test_entity_recovery_refuses_missing_target_scope() -> None:
    ledger = CandidateLedger([_entry()])
    result = recover_entity(_ticket(), ledger, context={})
    assert result == {"status": "SKIPPED", "reason": "missing_required_entity"}


def test_period_recovery_refuses_missing_target_duration() -> None:
    ledger = CandidateLedger([_entry()])
    result = recover_period(_ticket(), ledger, context={})
    assert result == {"status": "SKIPPED", "reason": "missing_target_duration"}
