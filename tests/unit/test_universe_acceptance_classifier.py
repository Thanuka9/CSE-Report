from __future__ import annotations

from typing import Any

from cse_financial_etl.validation.universe_acceptance import _classify_pipeline_errors


def _timeout(index: int) -> dict[str, str]:
    return {
        "issuer_name": f"Issuer {index}",
        "symbol": f"I{index}.N0000",
        "period_end": "2026-06-30",
        "stage": "EXTRACTION",
        "error": "PDF/OCR worker exceeded 480.0s and its process tree was terminated",
    }


def _baseline(
    allowed: list[dict[str, str]], *, maximum: int = 3
) -> dict[str, Any]:
    return {
        "max_quarantined_extraction_timeouts": maximum,
        "quarantined_extraction_timeouts": [
            {
                "issuer_name": row["issuer_name"],
                "symbol": row["symbol"],
                "period_end": row["period_end"],
            }
            for row in allowed
        ],
    }


def test_explicitly_allowlisted_process_tree_timeouts_are_quarantined() -> None:
    errors = [_timeout(1), _timeout(2), _timeout(3)]
    quarantined, unhandled = _classify_pipeline_errors(
        errors,
        expected_count=3,
        baseline=_baseline(errors),
    )
    assert [row["issuer_name"] for row in quarantined] == [
        row["issuer_name"] for row in errors
    ]
    assert all(row["classification"] == "KNOWN_TIMEOUT_QUARANTINE" for row in quarantined)
    assert unhandled == []


def test_new_timeout_is_not_hidden_by_available_quarantine_capacity() -> None:
    allowed = [_timeout(1), _timeout(2)]
    unexpected = _timeout(3)
    quarantined, unhandled = _classify_pipeline_errors(
        [*allowed, unexpected],
        expected_count=3,
        baseline=_baseline(allowed, maximum=3),
    )
    assert len(quarantined) == 2
    assert len(unhandled) == 1
    assert unhandled[0]["classification"] == "UNEXPECTED_EXTRACTION_TIMEOUT"


def test_quarantine_limit_fails_closed() -> None:
    errors = [_timeout(1), _timeout(2), _timeout(3), _timeout(4)]
    quarantined, unhandled = _classify_pipeline_errors(
        errors,
        expected_count=4,
        baseline=_baseline(errors, maximum=3),
    )
    assert len(quarantined) == 3
    assert len(unhandled) == 1
    assert unhandled[0]["classification"] == "QUARANTINE_LIMIT_EXCEEDED"


def test_non_timeout_or_missing_error_evidence_is_engineering_failure() -> None:
    errors = [
        {
            "stage": "DOWNLOAD",
            "error": "network failure",
        }
    ]
    quarantined, unhandled = _classify_pipeline_errors(
        errors,
        expected_count=2,
        baseline=_baseline([], maximum=3),
    )
    assert quarantined == []
    assert len(unhandled) == 2
    assert unhandled[-1]["classification"] == "PIPELINE_ERROR_EVIDENCE_MISMATCH"
