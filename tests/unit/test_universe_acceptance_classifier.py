from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _module() -> ModuleType:
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "check_universe_acceptance.py"
    spec = importlib.util.spec_from_file_location("check_universe_acceptance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _timeout(index: int) -> dict[str, str]:
    return {
        "issuer_name": f"Issuer {index}",
        "symbol": f"I{index}.N0000",
        "period_end": "2026-06-30",
        "stage": "EXTRACTION",
        "error": "PDF/OCR worker exceeded 480.0s and its process tree was terminated",
    }


def test_bounded_process_tree_timeouts_are_quarantined() -> None:
    module = _module()
    errors = [_timeout(1), _timeout(2), _timeout(3)]
    quarantined, unhandled = module._classify_pipeline_errors(
        errors,
        expected_count=3,
        max_quarantined_timeouts=3,
    )
    assert quarantined == errors
    assert unhandled == []


def test_quarantine_limit_fails_closed() -> None:
    module = _module()
    errors = [_timeout(1), _timeout(2), _timeout(3), _timeout(4)]
    quarantined, unhandled = module._classify_pipeline_errors(
        errors,
        expected_count=4,
        max_quarantined_timeouts=3,
    )
    assert len(quarantined) == 3
    assert len(unhandled) == 1
    assert unhandled[0]["classification"] == "QUARANTINE_LIMIT_EXCEEDED"


def test_non_timeout_or_missing_error_evidence_is_engineering_failure() -> None:
    module = _module()
    errors = [
        {
            "stage": "DOWNLOAD",
            "error": "network failure",
        }
    ]
    quarantined, unhandled = module._classify_pipeline_errors(
        errors,
        expected_count=2,
        max_quarantined_timeouts=3,
    )
    assert quarantined == []
    assert len(unhandled) == 2
    assert unhandled[-1]["classification"] == "PIPELINE_ERROR_EVIDENCE_MISMATCH"
