from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cse_financial_etl.v2.contracts.enums import EntityScope
from cse_financial_etl.v2.diagnostics.fact_diff import FactDiffClass
from cse_financial_etl.v2.diagnostics.golden import GoldenFact, evaluate_golden_gates, score_golden
from cse_financial_etl.v2.diagnostics.shadow import shadow_diff
from cse_financial_etl.v2.orchestration.cutover import (
    REQUIRED_GATES,
    CutoverNotReadyError,
    assert_v1_remains_default,
    evaluate_cutover,
)
from tests.v2.helpers import source_fact


def test_golden_scores_independent_dimensions() -> None:
    expected = (
        GoldenFact(
            metric_code="PAT",
            raw_value=Decimal("1234"),
            normalized_value=Decimal("1234000"),
            entity_scope=EntityScope.COMPANY,
            period_end=date(2026, 6, 30),
            duration_months=3,
            unit_scale=Decimal("1000"),
            page=1,
            reviewer="tester",
            review_date=date(2026, 9, 13),
        ),
    )
    predicted = (source_fact(),)
    report = score_golden(expected, predicted)
    assert report.source_reported_recall == 1.0
    assert report.entity_accuracy == 1.0
    assert report.numeric_accuracy == 1.0
    assert report.critical_wrong_populated == 0
    assert report.unit_accuracy == 1.0
    assert report.duration_accuracy == 1.0


def test_unlabeled_gold_unit_is_not_scored_as_one() -> None:
    expected = (
        GoldenFact(
            metric_code="PAT",
            raw_value=Decimal("1234"),
            normalized_value=Decimal("1234000"),
            entity_scope=EntityScope.COMPANY,
            period_end=date(2026, 6, 30),
            duration_months=3,
            unit_scale=None,
            page=1,
            reviewer="tester",
            review_date=date(2026, 9, 13),
        ),
    )
    predicted = (source_fact(),)
    report = score_golden(expected, predicted)
    assert report.true_positives == 1
    assert report.unit_accuracy == 1.0


def test_shadow_diff_breaks_down_by_metric() -> None:
    reference = (
        {
            "filing_version_id": "fv-1",
            "entity_scope": "COMPANY",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "comparison_role": "CURRENT",
            "metric_code": "PAT",
            "normalized_value": "1",
            "issuer_id": "issuer-1",
            "parser_path": "v2.native_pymupdf",
        },
    )
    current = (
        {
            "filing_version_id": "fv-1",
            "entity_scope": "COMPANY",
            "period_end": "2026-06-30",
            "duration_months": 3,
            "comparison_role": "CURRENT",
            "metric_code": "PAT",
            "normalized_value": "2",
            "issuer_id": "issuer-1",
            "parser_path": "v2.native_pymupdf",
        },
    )
    report = shadow_diff(reference, current)
    assert report["counts"][FactDiffClass.VALUE_CHANGED.value] == 1
    assert "PAT" in report["by_metric"]
    assert "issuer-1" in report["by_issuer"]
    assert "v2.native_pymupdf" in report["by_parser"]


def test_cutover_uses_v2_engine_before_institutional_ready() -> None:
    decision = evaluate_cutover({"canonical_document": True, "golden_corpus": False})
    assert decision.ready is False
    assert decision.default_engine == "V2"
    assert any(not gate.passed for gate in decision.gates if gate.name == "frozen_universe")
    assert_v1_remains_default(decision)


def test_ready_cutover_still_cannot_delete_v1() -> None:
    decision = evaluate_cutover(dict.fromkeys(REQUIRED_GATES, True))
    assert decision.ready is True
    with pytest.raises(CutoverNotReadyError):
        assert_v1_remains_default(decision)


def test_golden_gates_fail_on_numeric_mismatch() -> None:
    expected = (
        GoldenFact(
            metric_code="PAT",
            raw_value=Decimal("1234"),
            normalized_value=Decimal("1"),
            entity_scope=EntityScope.COMPANY,
            period_end=date(2026, 6, 30),
            duration_months=3,
            unit_scale=Decimal("1000"),
            page=1,
            reviewer="tester",
            review_date=date(2026, 9, 13),
        ),
    )
    report = score_golden(expected, (source_fact(),))
    gates = evaluate_golden_gates(report)
    assert gates.passed is False
    assert any("critical_wrong_populated" in item for item in gates.failures)
