from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cse_financial_etl.production.r4_hardening import (
    _harden_repository_rows,
    parse_period_end_strict,
    strict_last_traded_history,
)
from cse_financial_etl.storage.repository import Repository


def test_equivalent_period_title_formats_have_same_business_date() -> None:
    variants = (
        "Quarter ended 30 June 2026",
        "Quarter ended 30/06/2026",
        "Quarter ended 2026-06-30",
        "Period ending June 30, 2026",
    )
    assert {parse_period_end_strict(value) for value in variants} == {date(2026, 6, 30)}


def test_closing_price_presence_cannot_change_last_trade_resolution(tmp_path: Path) -> None:
    history = tmp_path / "data" / "raw" / "market" / "historical_prices"
    history.mkdir(parents=True)
    path = history / "historical_2026-06-30.json"
    base = {
        "symbol": "EX.N0000",
        "trade_date": "2026-06-30",
        "trade_price": "120.50",
    }
    path.write_text(json.dumps([base]), encoding="utf-8")
    first = strict_last_traded_history(tmp_path, "EX.N0000", date(2026, 6, 30))

    path.write_text(json.dumps([{**base, "closing_price": "999.99"}]), encoding="utf-8")
    second = strict_last_traded_history(tmp_path, "EX.N0000", date(2026, 6, 30))
    assert first == second
    assert first is not None and str(first[0]) == "120.50"


def test_cumulative_context_cannot_become_publishable_by_value_change(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "data")
    repository.start_run("run-meta", date(2026, 9, 10))
    repository.fact_rows = [
        {
            "fact_id": "a",
            "issuer_name": "Example PLC",
            "symbol": "EX.N0000",
            "period_end": "2026-09-30",
            "metric_code": "PAT",
            "metric_type": "MONETARY_ABSOLUTE",
            "normalized_value": "1",
            "status": "EXTRACTED",
            "validation_status": "PASSED",
            "review_status": "REVIEW",
            "duration_months": 9,
            "source_line": "Profit for the period 1",
        },
        {
            "fact_id": "b",
            "issuer_name": "Example PLC",
            "symbol": "EX.N0000",
            "period_end": "2026-09-30",
            "metric_code": "PBT",
            "metric_type": "MONETARY_ABSOLUTE",
            "normalized_value": "999999999999",
            "status": "EXTRACTED",
            "validation_status": "PASSED",
            "review_status": "REVIEW",
            "duration_months": 9,
            "source_line": "Profit before tax 999999999999",
        },
    ]
    _harden_repository_rows(repository)
    assert {row["status"] for row in repository.fact_rows} == {"NON_QUARTER_FLOW_WITHHELD"}
    assert all(row["normalized_value"] is None for row in repository.fact_rows)
