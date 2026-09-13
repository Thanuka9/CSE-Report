from __future__ import annotations

from datetime import date

from cse_financial_etl.v2.contracts.enums import PublicationStatus, ValidationStatus
from cse_financial_etl.v2.diagnostics.golden import (
    aggregate_golden_reports,
    evaluate_golden_gates,
    score_golden,
)
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from tests.v2.golden.corpus import load_synthetic_corpus


def test_synthetic_corpus_has_at_least_twenty_five_adjudicated_cases() -> None:
    corpus = load_synthetic_corpus()
    assert len(corpus) >= 25
    assert len({item.case_id for item in corpus}) == len(corpus)


def test_synthetic_golden_corpus_meets_engineering_gates() -> None:
    reports = []
    for case in load_synthetic_corpus():
        target = date(1999, 1, 1) if case.case_id == "query-target-period-ignored" else None
        _statements, facts, _derived, _metrics = run_filing_pipeline(
            case.document,
            issuer_id=case.issuer_id,
            expected_entity_scope=case.expected_entity_scope,
            target_period_end=target,
            accounting_regime=case.accounting_regime,
        )
        published = {
            fact.metric_code
            for fact in facts
            if fact.publication_status is not PublicationStatus.WITHHELD
            and fact.validation_status is not ValidationStatus.FAILED
        }
        forbidden = set(case.must_not_publish) & published
        assert not forbidden, f"{case.case_id} published {forbidden}"
        if case.expected:
            reports.append(score_golden(case.expected, facts))
    assert reports
    combined = aggregate_golden_reports(tuple(reports))
    gates = evaluate_golden_gates(combined)
    assert gates.passed, gates.failures
    assert combined.critical_wrong_populated == 0
    assert combined.true_positives == combined.expected_count
