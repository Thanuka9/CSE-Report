from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from cse_financial_etl.production.r4_hardening import (
    _harden_repository_rows,
    _source_metric_basis,
    build_canonical_master,
    build_disclosure_calendar,
    enforce_hash_bound_quarantines,
    parse_period_end_strict,
    strict_last_traded_history,
)
from cse_financial_etl.storage.repository import Repository


def _fact(
    *,
    metric: str,
    status: str = "EXTRACTED",
    duration: int | None = 3,
    issuer: str = "Example PLC",
    source_line: str = "Profit for the period 100",
) -> dict[str, object]:
    return {
        "fact_id": f"fact-{metric}",
        "filing_id": 1,
        "filing_sha256": "a" * 64,
        "issuer_name": issuer,
        "symbol": "EX.N0000",
        "period_end": "2026-06-30",
        "period_type": "QUARTER",
        "duration_months": duration,
        "metric_code": metric,
        "metric_type": "MONETARY_ABSOLUTE",
        "normalized_value": "100",
        "status": status,
        "validation_status": "PASSED",
        "review_status": "REVIEW",
        "missing_reason": None,
        "source_line": source_line,
    }


def test_period_title_parser_supports_real_date_variants() -> None:
    expected = date(2026, 6, 30)
    assert parse_period_end_strict("Quarter ended 30 June 2026") == expected
    assert parse_period_end_strict("Interim statements as at 30/06/2026") == expected
    assert parse_period_end_strict("Financial statements at 2026-06-30") == expected
    assert parse_period_end_strict("Period ending June 30, 2026") == expected


def test_historical_price_requires_trade_semantics_not_closing_price(tmp_path: Path) -> None:
    history = tmp_path / "data" / "raw" / "market" / "historical_prices"
    history.mkdir(parents=True)
    path = history / "historical_2026-06-29.json"
    path.write_text(
        json.dumps(
            [
                {
                    "symbol": "EX.N0000",
                    "trade_date": "2026-06-29",
                    "closing_price": "123.45",
                }
            ]
        ),
        encoding="utf-8",
    )
    assert strict_last_traded_history(tmp_path, "EX.N0000", date(2026, 6, 30)) is None

    path.write_text(
        json.dumps(
            [
                {
                    "symbol": "EX.N0000",
                    "trade_date": "2026-06-29",
                    "trade_price": "122.75",
                }
            ]
        ),
        encoding="utf-8",
    )
    resolved = strict_last_traded_history(tmp_path, "EX.N0000", date(2026, 6, 30))
    assert resolved == (resolved[0], date(2026, 6, 29), "CSE_LAST_TRADED_HISTORY")
    assert str(resolved[0]) == "122.75"


def test_reported_quarter_policy_withholds_non_3m_and_derived_base_flows(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "data")
    repository.start_run("run-1", date(2026, 9, 10))
    repository.fact_rows = [
        _fact(metric="PAT", duration=9),
        _fact(metric="TOP_LINE", status="EXTRACTED_DERIVED", duration=3),
        _fact(metric="EPS_SELECTED", status="EXTRACTED", duration=3),
    ]
    changes = _harden_repository_rows(repository)
    by_metric = {str(row["metric_code"]): row for row in repository.fact_rows}
    assert by_metric["PAT"]["status"] == "NON_QUARTER_FLOW_WITHHELD"
    assert by_metric["PAT"]["normalized_value"] is None
    assert by_metric["TOP_LINE"]["status"] == "DERIVED_Q4_NOT_PUBLISHABLE"
    assert by_metric["EPS_SELECTED"]["status"] == "EXTRACTED"
    assert changes["non_quarter_flow_withheld"] == 1
    assert changes["derived_q4_withheld"] == 1


def test_bank_operating_profit_after_financial_services_tax_is_not_substitute(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "data")
    repository.start_run("run-1", date(2026, 9, 10))
    repository.fact_rows = [
        _fact(
            metric="OPERATING_PROFIT",
            issuer="Example Bank PLC",
            source_line="Operating profit after taxes on financial services 1,000",
        )
    ]
    _harden_repository_rows(repository)
    assert repository.fact_rows[0]["status"] == "BANK_OPERATING_PROFIT_BASIS_MISMATCH"
    assert repository.fact_rows[0]["normalized_value"] is None


def test_canonical_master_keeps_issuer_id_across_legal_name_change(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()
    first = Repository(tmp_path / "data")
    first.market_rows = [
        {
            "security_id": 101,
            "company_name": "Old Name PLC",
            "symbol": "OLD.N0000",
        }
    ]
    _path, first_master = build_canonical_master(tmp_path, date(2026, 6, 30), first)
    issuer_id = first_master["issuers"][0]["issuer_id"]

    second = Repository(tmp_path / "data")
    second.market_rows = [
        {
            "security_id": 101,
            "company_name": "Renamed Company PLC",
            "symbol": "NEW.N0000",
        }
    ]
    _path, second_master = build_canonical_master(tmp_path, date(2026, 9, 30), second)
    current = [row for row in second_master["issuers"] if not row.get("active_to")]
    assert current[0]["issuer_id"] == issuer_id
    security = [row for row in second_master["securities"] if not row.get("active_to")][0]
    assert security["security_id"] == 101
    assert "OLD.N0000" in security["symbol_history"]


def test_disclosure_calendar_is_listing_segment_aware(tmp_path: Path) -> None:
    (tmp_path / "outputs").mkdir()
    master = {
        "issuers": [
            {
                "issuer_id": "I1",
                "legal_name": "Main PLC",
                "listing_segment": "MAIN",
                "fiscal_year_end_month": 12,
                "active_to": None,
            },
            {
                "issuer_id": "I2",
                "legal_name": "Empower PLC",
                "listing_segment": "EMPOWER",
                "fiscal_year_end_month": 12,
                "active_to": None,
            },
        ]
    }
    path = build_disclosure_calendar(
        tmp_path,
        date(2026, 9, 10),
        (date(2026, 3, 31), date(2026, 6, 30)),
        master,
    )
    rows = json.loads(path.read_text(encoding="utf-8"))
    lookup = {(row["issuer_id"], row["fiscal_quarter"]): row for row in rows}
    assert lookup[("I1", 1)]["requirement"] == "FULL_INTERIM_REQUIRED"
    assert lookup[("I2", 1)]["requirement"] == "SUPPLEMENTARY_DISCLOSURE_REQUIRED"
    assert lookup[("I2", 2)]["requirement"] == "FULL_INTERIM_REQUIRED"


def test_insurance_top_line_semantics_are_not_conflated() -> None:
    assert _source_metric_basis(
        {"metric_code": "TOP_LINE", "source_line": "Insurance revenue 100"},
        "INSURANCE",
    ) == "INSURANCE_REVENUE"
    assert _source_metric_basis(
        {"metric_code": "TOP_LINE", "source_line": "Gross written premium 100"},
        "INSURANCE",
    ) == "GROSS_WRITTEN_PREMIUM"
    assert _source_metric_basis(
        {"metric_code": "TOP_LINE", "source_line": "Net earned premium 100"},
        "INSURANCE",
    ) == "NET_EARNED_PREMIUM"


def test_known_timeout_quarantine_is_invalidated_when_hash_changes(tmp_path: Path) -> None:
    configs = tmp_path / "configs"
    configs.mkdir(parents=True)
    configs.joinpath("coverage_baseline.yml").write_text(
        """max_quarantined_extraction_timeouts: 1
quarantined_extraction_timeouts:
  - issuer_name: Known PLC
    symbol: KNOWN.N0000
    period_end: '2026-06-30'
""",
        encoding="utf-8",
    )
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    error = {
        "issuer_name": "Known PLC",
        "symbol": "KNOWN.N0000",
        "period_end": "2026-06-30",
        "stage": "EXTRACTION",
        "error": "PDF/OCR worker exceeded 480.0s and its process tree was terminated",
    }
    error_path = outputs / "pipeline_errors_2026-09-10.json"
    error_path.write_text(json.dumps([error]), encoding="utf-8")

    filing_dir = tmp_path / "data" / "raw" / "filings" / "Known_PLC"
    filing_dir.mkdir(parents=True)
    pointer = filing_dir / "2026-06-30_42.current.json"
    pointer.write_text(
        json.dumps({"filing_id": 42, "sha256": "a" * 64}), encoding="utf-8"
    )
    first = enforce_hash_bound_quarantines(tmp_path, date(2026, 9, 10))
    assert first["mismatches"] == 0

    pointer.write_text(
        json.dumps({"filing_id": 43, "sha256": "b" * 64}), encoding="utf-8"
    )
    second = enforce_hash_bound_quarantines(tmp_path, date(2026, 9, 10))
    assert second["mismatches"] == 1
    errors = json.loads(error_path.read_text(encoding="utf-8"))
    assert errors[-1]["stage"] == "QUARANTINE_INTEGRITY"
