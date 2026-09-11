from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.recovery.failure_diagnoser import FailureTicket
from cse_financial_etl.recovery.numeric_recovery import recover_numeric
from cse_financial_etl.recovery.semantic_recovery import recover_semantic
from cse_financial_etl.recovery.unit_recovery import recover_unit
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.transformation.ratios import _index_facts
from cse_financial_etl.extraction.statement_extractor import ExtractedFact


def _ticket(concept: str = "PAT") -> FailureTicket:
    return FailureTicket("t1", concept, "SEMANTIC_CONFLICT", "concept", "test")


def _entry(**overrides: object) -> LedgerEntry:
    values: dict[str, object] = {
        "entry_id": "e1",
        "tunnel": "A",
        "concept": "PAT",
        "status": "rejected",
        "raw_value": Decimal("10"),
        "normalized_value": Decimal("10000"),
        "entity": "COMPANY",
        "period_end": "2026-06-30",
        "duration_months": 3,
        "comparison_role": "CURRENT",
        "unit": "LKR",
        "scale_factor": 1000,
        "page": 1,
        "bbox": None,
        "label": "Profit for the period",
        "score": 0.4,
        "reasons": ["SEMANTIC_CONFLICT"],
        "evidence": {"semantic_score": 0.4},
    }
    values.update(overrides)
    return LedgerEntry(**values)  # type: ignore[arg-type]


def test_unit_recovery_abstains_on_mixed_filing_scales() -> None:
    entry = _entry(unit=None, scale_factor=None, normalized_value=None, status="unresolved")
    ledger = CandidateLedger([entry])
    outcome = recover_unit(_ticket(), ledger, context={"unit_texts": ["LKR '000", "LKR Mn"]})
    assert outcome["status"] == "NO_CHANGE"
    assert outcome["reason"] == "ambiguous_unit_evidence"
    assert entry.unit is None and entry.scale_factor is None


def test_unit_recovery_never_overwrites_known_dimension() -> None:
    entry = _entry(unit="USD", scale_factor=None, normalized_value=None, status="unresolved")
    ledger = CandidateLedger([entry])
    outcome = recover_unit(_ticket(), ledger, context={"unit_texts": ["LKR '000"]})
    assert outcome["status"] == "NO_CHANGE"
    assert entry.unit == "USD" and entry.scale_factor is None
    assert "UNIT_RECOVERY_CURRENCY_CONFLICT" in entry.reasons


def test_semantic_recovery_cannot_borrow_another_rows_label() -> None:
    entry = _entry(label="Total comprehensive income for the period")
    ledger = CandidateLedger([entry])
    outcome = recover_semantic(
        _ticket(),
        ledger,
        context={"row_labels": ["Profit for the period"]},
    )
    assert outcome["status"] == "NO_CHANGE"
    assert entry.status == "rejected"


def test_semantic_recovery_uses_own_strong_label_and_preserves_score() -> None:
    entry = _entry(label="Profit for the period")
    ledger = CandidateLedger([entry])
    outcome = recover_semantic(_ticket(), ledger, context={"row_labels": []})
    assert outcome["status"] == "RECOVERED"
    assert entry.status == "unresolved"
    assert float(entry.evidence["semantic_score"]) >= 0.8


def test_numeric_recovery_ignores_filing_wide_unowned_numbers() -> None:
    entry = _entry(raw_value=None, normalized_value=None, status="unresolved", evidence={})
    ledger = CandidateLedger([entry])
    outcome = recover_numeric(_ticket(), ledger, context={"raw_numeric_texts": ["999,999"]})
    assert outcome["status"] == "NO_CHANGE"
    assert entry.raw_value is None and entry.normalized_value is None


def test_numeric_recovery_reparses_only_entry_owned_token() -> None:
    entry = _entry(
        raw_value=None,
        normalized_value=None,
        status="unresolved",
        evidence={"raw_numeric_text": "1,234"},
    )
    ledger = CandidateLedger([entry])
    outcome = recover_numeric(_ticket(), ledger, context={"raw_numeric_texts": ["999,999"]})
    assert outcome["status"] == "RECOVERED"
    assert entry.raw_value == Decimal("1234")
    assert entry.normalized_value == Decimal("1234000")


def _fact(value: str) -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="FLOW",
        raw_text=value,
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Profit for the period",
        unit_source_text="LKR",
        confidence="HIGH",
        status="EXTRACTED",
        semantic_confidence=1.0,
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
    )


def test_ratio_index_marks_duplicate_same_period_metric_ambiguous() -> None:
    index = _index_facts([(object(), [_fact("10")]), (object(), [_fact("20")])])
    assert index[("Acme PLC", date(2026, 6, 30), "PAT")] is None
