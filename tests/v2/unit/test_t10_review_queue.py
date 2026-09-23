from __future__ import annotations

from cse_financial_etl.v2.diagnostics.experiments import build_t10_review_queue


def test_t10_queue_omits_comparator_values_and_is_not_gold() -> None:
    split = {"dev": ["JKH.N0000"], "holdout": ["HAYL.N0000"]}
    rows = [
        {
            "issue_id": "JKH-PAT-1",
            "pdf_sha": "a" * 64,
            "issuer": "JKH.N0000",
            "metric": "PAT",
            "page": 2,
            "disagreement_class": "VALUE_DISAGREEMENT",
            "v1_value": "999",
            "v2_value": "111",
        },
        {
            "issue_id": "JKH-PBT-2",
            "pdf_sha": "a" * 64,
            "issuer": "JKH.N0000",
            "metric": "PBT",
            "page": 2,
            "disagreement_class": "AGREEMENT",
            "v1_value": "1",
            "v2_value": "1",
        },
        {
            "issue_id": "HAYL-PAT-1",
            "pdf_sha": "b" * 64,
            "issuer": "HAYL.N0000",
            "metric": "PAT",
            "page": 1,
            "disagreement_class": "REFERENCE_ONLY_DISAGREEMENT",
            "v1_value": "50",
        },
    ]
    queue = build_t10_review_queue(rows, split=split, limit=40)
    assert queue["item_count"] == 2
    first, second = queue["items"]
    assert first["issuer"] == "JKH.N0000"
    assert first["split"] == "DEV"
    assert first["adjudication_status"] == "NOT_STARTED"
    assert first["source_truth_status"] == "NOT_ADJUDICATED"
    assert "v1_value" not in first
    assert "v2_value" not in first
    assert "normalized_value" not in first
    assert second["split"] == "HOLDOUT"
    assert "not gold" in queue["note"].casefold() or "not source truth" in queue["note"].casefold()
