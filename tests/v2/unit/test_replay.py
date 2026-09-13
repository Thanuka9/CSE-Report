from __future__ import annotations

from cse_financial_etl.v2.diagnostics.fact_diff import (
    FactDiffClass,
    classify_fact_pair,
    diff_fact_populations,
)
from cse_financial_etl.v2.diagnostics.replay import collect_runtime_pin, replay_fact_diff


def _fact(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "filing_version_id": "fv-1",
        "entity_scope": "COMPANY",
        "period_end": "2026-06-30",
        "duration_months": 3,
        "comparison_role": "CURRENT",
        "metric_code": "PAT",
        "normalized_value": "1000",
        "validation_status": "PASSED",
        "review_status": "REVIEW",
        "publication_status": "ELIGIBLE",
    }
    payload.update(overrides)
    return payload


def test_fact_diff_classifies_identity_changes() -> None:
    reference = _fact()
    assert classify_fact_pair(reference, _fact()) is FactDiffClass.UNCHANGED
    assert classify_fact_pair(reference, None) is FactDiffClass.LOST
    assert classify_fact_pair(None, reference) is FactDiffClass.NEW
    assert (
        classify_fact_pair(reference, _fact(normalized_value="999")) is FactDiffClass.VALUE_CHANGED
    )
    assert (
        classify_fact_pair(reference, _fact(entity_scope="GROUP")) is FactDiffClass.CONTEXT_CHANGED
    )
    assert (
        classify_fact_pair(reference, _fact(publication_status="WITHHELD"))
        is FactDiffClass.STATUS_CHANGED
    )


def test_population_diff_counts_are_complete() -> None:
    counts = diff_fact_populations(
        (_fact(), _fact(metric_code="PBT")),
        (_fact(), _fact(metric_code="NAVPS")),
    )
    assert counts[FactDiffClass.UNCHANGED] == 1
    assert counts[FactDiffClass.LOST] == 1
    assert counts[FactDiffClass.NEW] == 1


def test_runtime_pin_is_populated() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    pin = collect_runtime_pin(root)
    assert pin.code_sha
    assert pin.python_version
    assert pin.pymupdf_version
    report = replay_fact_diff((_fact(),), (_fact(normalized_value="2"),))
    assert report[FactDiffClass.VALUE_CHANGED.value] == 1
