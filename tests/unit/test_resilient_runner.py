from __future__ import annotations

import time
from datetime import date
from decimal import Decimal
from multiprocessing import get_context
from multiprocessing.connection import Connection
from pathlib import Path

import pytest

from cse_financial_etl.extraction.resilient_runner import (
    ProcessingTimeoutError,
    _await_process_payload,
    extract_filing_resilient,
)
from cse_financial_etl.extraction.statement_extractor import ExtractedFact


def _fact(value: str) -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text=value,
        raw_value=Decimal(value),
        normalized_value=Decimal(value),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Profit for the period",
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
    )


def _sleep_with_open_pipe(send: Connection) -> None:
    try:
        time.sleep(30)
    finally:
        send.close()


def test_successful_result_cache_resumes_without_reextracting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from cse_financial_etl.extraction import statement_extractor

    source = tmp_path / "filing.pdf"
    source.write_bytes(b"%PDF-test")
    calls = {"count": 0}

    def fake_extract(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        calls["count"] += 1
        return [_fact(str(calls["count"]))]

    monkeypatch.setattr(statement_extractor, "extract_filing", fake_extract)
    cache = tmp_path / "cache"
    kwargs = {
        "project_root": tmp_path,
        "result_cache_dir": cache,
        "process_timeout_seconds": 0,
        "cache_namespace": "sha-a:config-a",
        "ocr_enabled": False,
    }
    first = extract_filing_resilient(
        source,
        "Acme PLC",
        "ACM.N0000",
        date(2026, 6, 30),
        **kwargs,
    )
    second = extract_filing_resilient(
        source,
        "Acme PLC",
        "ACM.N0000",
        date(2026, 6, 30),
        **kwargs,
    )

    assert calls["count"] == 1
    assert first[0].normalized_value == Decimal("1")
    assert second[0].normalized_value == Decimal("1")

    changed = extract_filing_resilient(
        source,
        "Acme PLC",
        "ACM.N0000",
        date(2026, 6, 30),
        project_root=tmp_path,
        result_cache_dir=cache,
        process_timeout_seconds=0,
        cache_namespace="sha-b:config-a",
        ocr_enabled=False,
    )
    assert calls["count"] == 2
    assert changed[0].normalized_value == Decimal("2")


def test_process_timeout_terminates_stuck_worker_tree() -> None:
    context = get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_sleep_with_open_pipe, args=(send,), daemon=False)
    process.start()
    send.close()
    try:
        with pytest.raises(ProcessingTimeoutError):
            _await_process_payload(process, receive, timeout_seconds=0.25)
    finally:
        receive.close()
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
    assert not process.is_alive()
