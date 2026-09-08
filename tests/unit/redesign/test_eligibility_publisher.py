"""Audit findings 2, 5, 6, 8 and gap A9: shared eligibility, abstention, preserved
FAILED, machine-only review status, metric-specific absence codes, provenance fields,
and the publisher/final_validator import cycle."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from cse_financial_etl.cli import app
from cse_financial_etl.contracts.eligibility import (
    DURATION_UNKNOWN,
    ENTITY_UNKNOWN,
    PERIOD_UNKNOWN,
    UNIT_UNRESOLVED,
    evaluate_eligibility,
)
from cse_financial_etl.domain.enums import MACHINE_ABSENCE_STATUSES, MissingReason
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.facts.publisher import (
    COMPILER_DISABLED,
    COMPILER_NO_STATEMENTS,
    compiler_routing,
    publish_from_compiler,
)
from cse_financial_etl.facts.query_engine import QueriedFact, query_target_facts
from cse_financial_etl.resolution.arbiter import arbitrate_candidates
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.validation.final_validator import validate_source_fact

ROOT = Path(__file__).resolve().parents[3]


def _entry(**kwargs: object) -> LedgerEntry:
    base: dict[str, object] = dict(
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
        score=0.9,
        evidence={"semantic_score": 1.0},
    )
    base.update(kwargs)
    return LedgerEntry(**base)  # type: ignore[arg-type]


def _layout_fact(**kwargs: object) -> ExtractedFact:
    base: dict[str, object] = dict(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="FLOW",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Profit for the period 100",
        unit_source_text="Rs.'000",
        confidence="HIGH",
        status="EXTRACTED",
        duration_months=3,
        comparison_role="CURRENT",
        validation_status="NOT_VALIDATED",
        review_status="APPROVED",
    )
    base.update(kwargs)
    return ExtractedFact(**base)  # type: ignore[arg-type]


def _report(statements: int, *, requested: bool = True) -> dict:
    return {
        "filing_sha": "abc",
        "tunnel_a": {"statements": statements, "compile_requested": requested, "native_compiler_success": statements > 0},
        "tunnel_b": {"invoked": False},
        "resolver_c": {},
    }


# --- finding 5: shared eligibility contract -------------------------------------------


def test_eligibility_requires_unit_duration_period_entity() -> None:
    bare = _entry(unit=None, duration_months=None, period_end=None, entity=None, scale_factor=None)
    result = evaluate_eligibility(bare, required_entity="COMPANY", target_duration=3, target_period_end="2026-06-30")
    assert not result.eligible
    for code in (UNIT_UNRESOLVED, DURATION_UNKNOWN, PERIOD_UNKNOWN, ENTITY_UNKNOWN):
        assert code in result.reasons
    good = evaluate_eligibility(_entry(), required_entity="COMPANY", target_duration=3, target_period_end="2026-06-30")
    assert good.eligible and good.reasons == ()


def test_final_validator_fails_pat_without_unit() -> None:
    check = validate_source_fact(
        _entry(unit=None, status="accepted"),
        required_entity="COMPANY",
        target_duration=3,
        target_period_end="2026-06-30",
        concept="PAT",
    )
    assert check.status == "FAIL"
    assert UNIT_UNRESOLVED in check.reasons


def test_arbiter_abstains_on_equal_score_conflicting_values() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="layout", normalized_value=Decimal("100"), evidence={"candidate_origin": "layout_geometry"}))
    ledger.add(_entry(entry_id="compiled", normalized_value=Decimal("999")))
    decisions = arbitrate_candidates(ledger, required_entity="COMPANY", target_duration=3, target_period_end="2026-06-30")
    pat = next(d for d in decisions if d.concept == "PAT")
    assert pat.status == "UNRESOLVED"
    assert pat.selected is None
    assert "AMBIGUOUS_EQUAL_SCORE" in pat.reasons
    assert all(e.status == "unresolved" for e in ledger.for_concept("PAT"))
    assert not any("layout_assist_tiebreak" in e.reasons for e in ledger.entries)


def test_arbiter_treats_equal_values_as_corroboration() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="a", normalized_value=Decimal("100")))
    ledger.add(_entry(entry_id="b", normalized_value=Decimal("100"), page=2))
    decisions = arbitrate_candidates(ledger, required_entity="COMPANY", target_duration=3, target_period_end="2026-06-30")
    pat = next(d for d in decisions if d.concept == "PAT")
    assert pat.status == "SELECTED" and pat.selected is not None
    assert pat.selected.evidence["corroborated_by"] == ["b"] or pat.selected.evidence["corroborated_by"] == ["a"]


def test_arbiter_keeps_unresolved_dimensions_unresolved_not_rejected() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="nounit", unit=None))
    arbitrate_candidates(ledger, required_entity="COMPANY", target_duration=3, target_period_end="2026-06-30")
    entry = ledger.for_concept("PAT")[0]
    assert entry.status == "unresolved"
    assert UNIT_UNRESOLVED in entry.reasons


# --- finding 5/6: publisher never upgrades FAILED, never grants approval ----------------


def test_publisher_preserves_failed_validation_from_layout_evidence() -> None:
    layout = _layout_fact(validation_status="FAILED")
    entry = _entry(status="accepted", evidence={"candidate_origin": "layout_geometry", "semantic_score": 1.0})
    queried = [QueriedFact("PAT", "PAT", entry, "EXTRACTED")]
    published, stats = publish_from_compiler(
        queried=queried,
        layout_facts=[layout],
        report=_report(0),
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        required_entity="COMPANY",
    )
    pat = next(f for f in published if f.metric_code == "PAT")
    assert pat.validation_status == "FAILED"
    assert pat.review_status == "REVIEW"
    evidence = json.loads(pat.evidence_json)
    assert evidence["prior_validation_status"] == "FAILED"
    assert evidence["publication_routing"] == "layout_assist_only"
    assert evidence["native_compiler_success"] is False
    assert evidence["explicit_fallback"] == COMPILER_NO_STATEMENTS
    assert stats["layout_assist_selected"] == 1


def test_publisher_never_approves_and_keeps_compiler_provenance_separate() -> None:
    entry = _entry(status="accepted")
    queried = [QueriedFact("PAT", "PAT", entry, "EXTRACTED")]
    published, stats = publish_from_compiler(
        queried=queried,
        layout_facts=[_layout_fact(review_status="APPROVED", validation_status="PASSED")],
        report=_report(3),
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        required_entity="COMPANY",
    )
    assert all(f.review_status == "REVIEW" for f in published)
    pat = next(f for f in published if f.metric_code == "PAT")
    evidence = json.loads(pat.evidence_json)
    assert evidence["publication_routing"] == "statement_compiler"
    assert evidence["extraction_origin"] == "compiler_geometry"
    assert evidence["native_compiler_success"] is True
    assert evidence["explicit_fallback"] is None
    assert pat.validation_status == "PASSED"
    assert stats["compiler_selected"] == 1


def test_publisher_fails_and_withholds_value_when_final_check_fails() -> None:
    entry = _entry(status="accepted", unit=None)
    queried = [QueriedFact("PAT", "PAT", entry, "EXTRACTED")]
    published, stats = publish_from_compiler(
        queried=queried,
        layout_facts=[],
        report=_report(3),
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        required_entity="COMPANY",
    )
    pat = next(f for f in published if f.metric_code == "PAT")
    assert pat.status == "VALUE_CONTEXT_UNRESOLVED"
    assert pat.normalized_value is None
    assert pat.validation_status == "FAILED"
    assert stats["final_check_failures"] == 1


def test_compiler_routing_never_labels_zero_statements_as_compiler() -> None:
    assert compiler_routing(_report(0)) == ("layout_assist_only", False, COMPILER_NO_STATEMENTS)
    assert compiler_routing(_report(0, requested=False)) == ("layout_assist_only", False, COMPILER_DISABLED)
    assert compiler_routing(_report(2)) == ("statement_compiler", True, None)


# --- finding 8: metric-specific absence codes -------------------------------------------


def test_query_engine_emits_metric_specific_absence_codes() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="ytd", status="rejected", duration_months=6, reasons=["YTD_CANNOT_SATISFY_3M"]))
    queried = {q.metric_code: q for q in query_target_facts(ledger, entity="COMPANY", period_end=date(2026, 6, 30))}
    assert queried["PAT"].status == str(MissingReason.ONLY_CUMULATIVE_CANDIDATES_LOCATED)
    assert queried["PAT"].trace is not None and queried["PAT"].trace.candidates_seen == 1
    assert queried["PBT"].status == str(MissingReason.SEARCH_INCOMPLETE)

    after_recovery = {
        q.metric_code: q
        for q in query_target_facts(ledger, entity="COMPANY", period_end=date(2026, 6, 30), recovery_attempted=True)
    }
    assert after_recovery["PBT"].status == str(MissingReason.NOT_LOCATED_AFTER_CONFIGURED_RECOVERY)
    for fact in list(queried.values()) + list(after_recovery.values()):
        assert fact.status != "SOURCE_CONFIRMED_NOT_REPORTED"
        assert fact.status != "CUMULATIVE_ONLY"
        if fact.status != "EXTRACTED":
            assert fact.status in MACHINE_ABSENCE_STATUSES


def test_query_engine_reports_ambiguity_not_absence() -> None:
    ledger = CandidateLedger()
    ledger.add(_entry(entry_id="a", normalized_value=Decimal("100")))
    ledger.add(_entry(entry_id="b", normalized_value=Decimal("999")))
    arbitrate_candidates(ledger, required_entity="COMPANY", target_duration=3, target_period_end="2026-06-30")
    queried = {q.metric_code: q for q in query_target_facts(ledger, entity="COMPANY", period_end=date(2026, 6, 30))}
    assert queried["PAT"].status == str(MissingReason.AMBIGUOUS_CANDIDATES)


# --- finding 2: CLI exposes the compiler switch ------------------------------------------


def test_cli_exposes_compile_switch() -> None:
    result = CliRunner().invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--no-compile" in result.output
    assert "--tunnel-b-always" in result.output


# --- finding 11 / gap A9: no import cycle in a fresh interpreter --------------------------


def test_final_validator_imports_first_in_fresh_process() -> None:
    for module in (
        "cse_financial_etl.validation.final_validator",
        "cse_financial_etl.facts.publisher",
        "cse_financial_etl.contracts.eligibility",
    ):
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=ROOT,
            env={**__import__('os').environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, f"{module}: {proc.stderr}"


def test_contracts_package_is_dependency_neutral() -> None:
    src = (ROOT / "src" / "cse_financial_etl" / "contracts").rglob("*.py")
    for path in src:
        text = path.read_text(encoding="utf-8")
        for forbidden in ("cse_financial_etl.facts", "cse_financial_etl.validation", "cse_financial_etl.extraction",
                          "cse_financial_etl.reporting", "cse_financial_etl.tunnels"):
            assert forbidden not in text, f"{path.name} imports {forbidden}"
