from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.config import GitIdentity, code_version, git_identity
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.balance_sheet import (
    evaluate_balance_sheet_identity,
    evaluate_balance_sheet_sanity,
)
from cse_financial_etl.validation.cross_metric import evaluate_cross_metric_context
from cse_financial_etl.validation.equation_engine import ValidationOutcome
from cse_financial_etl.validation.profit_bridge import evaluate_pat_tax_bridge
from cse_financial_etl.validation.registry import build_default_equation_engine
from cse_financial_etl.validation.retry_controller import RetryController, strategy_for


def _fact(code: str, value: str, **overrides: object) -> ExtractedFact:
    payload = {
        "issuer_name": "Acme PLC",
        "symbol": "ACM.N0000",
        "period_end": date(2026, 6, 30),
        "metric_code": code,
        "metric_type": "MONETARY_ABSOLUTE",
        "raw_text": value,
        "raw_value": Decimal(value),
        "normalized_value": Decimal(value),
        "currency": "LKR",
        "scale_factor": 1,
        "entity_scope": "COMPANY",
        "source_page": 1,
        "source_line": code,
        "unit_source_text": "Rs.",
        "confidence": "HIGH",
        "status": "EXTRACTED",
        "comparison_role": "CURRENT",
        "duration_months": 3 if code in {"PAT", "PBT", "TOP_LINE", "OPERATING_PROFIT"} else None,
        "validation_status": "PASSED",
        "review_status": "APPROVED",
        "entity_confidence": 0.9,
    }
    payload.update(overrides)
    return ExtractedFact(**payload)  # type: ignore[arg-type]


def test_balance_sheet_identity_pass_and_fail() -> None:
    ok = {
        "TOTAL_ASSETS": _fact("TOTAL_ASSETS", "1000"),
        "TOTAL_LIABILITIES": _fact("TOTAL_LIABILITIES", "400"),
        "TOTAL_EQUITY": _fact("TOTAL_EQUITY", "600"),
    }
    assert evaluate_balance_sheet_identity(ok).outcome == ValidationOutcome.PASS
    bad = {
        "TOTAL_ASSETS": _fact("TOTAL_ASSETS", "1000"),
        "TOTAL_LIABILITIES": _fact("TOTAL_LIABILITIES", "100"),
        "TOTAL_EQUITY": _fact("TOTAL_EQUITY", "600"),
    }
    assert evaluate_balance_sheet_identity(bad).outcome == ValidationOutcome.FAIL


def test_balance_sheet_sanity_assets_below_equity() -> None:
    facts = {
        "TOTAL_ASSETS": _fact("TOTAL_ASSETS", "100"),
        "TOTAL_EQUITY": _fact("TOTAL_EQUITY", "200"),
    }
    assert evaluate_balance_sheet_sanity(facts).outcome == ValidationOutcome.FAIL


def test_cross_metric_flags_mixed_duration() -> None:
    facts = {
        "PAT": _fact("PAT", "10", duration_months=3),
        "PBT": _fact("PBT", "12", duration_months=6),
    }
    result = evaluate_cross_metric_context(facts)
    assert result.outcome == ValidationOutcome.FAIL


def test_pat_tax_bridge_not_applicable_without_tax() -> None:
    facts = {"PBT": _fact("PBT", "100"), "PAT": _fact("PAT", "70")}
    assert evaluate_pat_tax_bridge(facts).outcome == ValidationOutcome.NOT_APPLICABLE


def test_default_registry_evaluates_all_core_rules() -> None:
    engine = build_default_equation_engine()
    facts = {
        "TOTAL_ASSETS": _fact("TOTAL_ASSETS", "1000"),
        "TOTAL_LIABILITIES": _fact("TOTAL_LIABILITIES", "400"),
        "TOTAL_EQUITY": _fact("TOTAL_EQUITY", "600"),
        "PAT": _fact("PAT", "10"),
        "PBT": _fact("PBT", "12"),
    }
    results = engine.evaluate(facts)
    assert {item.rule_id for item in results} >= {
        "BALANCE_SHEET_IDENTITY",
        "BALANCE_SHEET_SANITY",
        "CROSS_METRIC_CONTEXT_INCONSISTENT",
        "PAT_TAX_BRIDGE",
        "EPS_RECONCILIATION",
        "NAVPS_RECONCILIATION",
    }


def test_retry_controller_recovers_on_second_extract(tmp_path: Path) -> None:
    failing = [
        _fact("TOTAL_ASSETS", "1000"),
        _fact("TOTAL_LIABILITIES", "100"),
        _fact("TOTAL_EQUITY", "600"),
    ]
    recovered = [
        _fact("TOTAL_ASSETS", "1000"),
        _fact("TOTAL_LIABILITIES", "400"),
        _fact("TOTAL_EQUITY", "600"),
    ]
    calls = {"n": 0}

    def extract(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return recovered

    def validate(facts):  # type: ignore[no-untyped-def]
        mapped = {fact.metric_code: fact for fact in facts}
        return [evaluate_balance_sheet_identity(mapped), evaluate_balance_sheet_sanity(mapped)]

    controller = RetryController(max_rounds=2)
    outcome = controller.run(
        failing,
        pdf_path=tmp_path / "x.pdf",
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        period_end=date(2026, 6, 30),
        validate=validate,
        extract=extract,
        lineage_dir=tmp_path,
    )
    assert outcome.recovered is True
    assert calls["n"] >= 1
    assert (tmp_path / "retry_lineage.json").exists()
    assert strategy_for(evaluate_balance_sheet_identity(failing and {f.metric_code: f for f in failing})) == (
        "RESELECT_SOFP_CANDIDATES"
    )


def test_git_identity_and_code_version(tmp_path: Path) -> None:
    assert code_version()
    identity = git_identity(Path(__file__).resolve().parents[2])
    assert isinstance(identity, GitIdentity)
    payload = identity.as_dict()
    assert "git_commit_sha" in payload
    assert "git_branch" in payload
    assert "working_tree_dirty" in payload
