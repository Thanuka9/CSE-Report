from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml

from cse_financial_etl.domain.periods import supporting_periods
from cse_financial_etl.production.runtime import (
    ProductionRunCapture,
    _block_legacy_corrections,
    assert_production_as_of,
    promote_staged_run,
    revision_safe_download_filing,
    strict_resolve_quarter_end_price,
)
from cse_financial_etl.sources.cse import Filing
from cse_financial_etl.storage.repository import Repository
from cse_financial_etl.validation.universe_acceptance import evaluate_universe_acceptance


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _publishable_row(
    *, issuer: str = "Example PLC", metric: str = "PAT", value: str = "100"
) -> dict[str, Any]:
    return {
        "issuer_name": issuer,
        "symbol": "EX.N0000",
        "period_end": "2026-06-30",
        "metric_code": metric,
        "metric_type": "MONETARY_ABSOLUTE",
        "status": "EXTRACTED",
        "normalized_value": value,
        "review_status": "REVIEW",
        "validation_status": "PASSED",
        "comparison_role": "CURRENT",
        "duration_months": "3" if metric in {"PAT", "PBT", "TOP_LINE"} else "",
    }


def _acceptance_files(
    tmp_path: Path,
    *,
    facts: list[dict[str, Any]],
    errors: list[dict[str, Any]] | None = None,
    baseline: dict[str, Any] | None = None,
    manifest_overrides: dict[str, Any] | None = None,
) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    errors = errors or []
    manifest: dict[str, Any] = {
        "run_id": "run-1",
        "git_commit_sha": "abc123",
        "issuer_count": 1,
        "downloaded_filing_count": 1,
        "extracted_filing_count": 1,
        "pipeline_error_count": len(errors),
        "fact_status_counts": {"EXTRACTED": len(facts), "EXTRACTED_DERIVED": 0},
        "production_gates": {"hits": []},
        "retry_summary": {},
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    base = baseline or {
        "min_draft_publishable": len(facts),
        "min_extracted_plus_derived": len(facts),
        "min_issuer_count": 1,
        "min_downloaded_filing_count": 1,
        "min_extracted_filing_count": 1,
        "max_quarantined_extraction_timeouts": 0,
    }
    paths = {
        "manifest": tmp_path / "manifest.json",
        "review": tmp_path / "review.csv",
        "facts": tmp_path / "facts.csv",
        "errors": tmp_path / "errors.json",
        "baseline": tmp_path / "baseline.yml",
    }
    paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
    _write_csv(paths["facts"], facts)
    _write_csv(
        paths["review"],
        [
            {
                "issuer_name": "Example PLC",
                "period_end": "2026-06-30",
                "metric_code": "PAT",
                "reason": "TEST_REVIEW",
            }
        ],
    )
    paths["errors"].write_text(json.dumps(errors), encoding="utf-8")
    paths["baseline"].write_text(yaml.safe_dump(base), encoding="utf-8")
    return paths


def _evaluate(paths: dict[str, Path]) -> dict[str, Any]:
    return evaluate_universe_acceptance(
        manifest_path=paths["manifest"],
        review_path=paths["review"],
        facts_path=paths["facts"],
        errors_path=paths["errors"],
        baseline_path=paths["baseline"],
    )


def test_known_timeout_is_quarantined_but_new_timeout_fails(tmp_path: Path) -> None:
    known = {
        "issuer_name": "Known PLC",
        "symbol": "KNOWN.N0000",
        "period_end": "2026-06-30",
        "stage": "EXTRACTION",
        "error": "PDF/OCR worker exceeded 480.0s and its process tree was terminated",
    }
    baseline = {
        "min_draft_publishable": 1,
        "min_extracted_plus_derived": 1,
        "min_issuer_count": 1,
        "min_downloaded_filing_count": 1,
        "min_extracted_filing_count": 1,
        "max_quarantined_extraction_timeouts": 1,
        "quarantined_extraction_timeouts": [
            {
                "issuer_name": "Known PLC",
                "symbol": "KNOWN.N0000",
                "period_end": "2026-06-30",
            }
        ],
    }
    paths = _acceptance_files(
        tmp_path / "known",
        facts=[_publishable_row()],
        errors=[known],
        baseline=baseline,
    )
    accepted = _evaluate(paths)
    assert accepted["quarantined_pipeline_error_count"] == 1
    assert accepted["unhandled_pipeline_error_count"] == 0
    assert accepted["acceptance"] == "ENGINEERING_PASS"

    unexpected = {**known, "issuer_name": "Unexpected PLC", "symbol": "NEW.N0000"}
    paths = _acceptance_files(
        tmp_path / "unexpected",
        facts=[_publishable_row()],
        errors=[unexpected],
        baseline=baseline,
    )
    rejected = _evaluate(paths)
    assert rejected["unhandled_pipeline_error_count"] == 1
    assert rejected["unhandled_pipeline_errors"][0]["classification"] == (
        "UNEXPECTED_EXTRACTION_TIMEOUT"
    )
    assert rejected["acceptance"] == "ENGINEERING_FAILURES_PRESENT"


def test_metric_and_sector_floors_cannot_hide_behind_aggregate_count(tmp_path: Path) -> None:
    facts = [
        _publishable_row(issuer="Example Bank PLC", metric="PAT"),
        _publishable_row(issuer="General Example PLC", metric="PBT"),
    ]
    baseline = {
        "min_draft_publishable": 2,
        "min_extracted_plus_derived": 2,
        "min_issuer_count": 1,
        "min_downloaded_filing_count": 1,
        "min_extracted_filing_count": 1,
        "max_quarantined_extraction_timeouts": 0,
        "min_publishable_by_metric": {"PAT": 2},
        "min_publishable_by_sector_metric": {"BANK": {"PAT": 2}},
    }
    result = _evaluate(
        _acceptance_files(tmp_path, facts=facts, baseline=baseline)
    )
    codes = {row["code"] for row in result["coverage_regressions"]}
    assert "METRIC_COVERAGE_REGRESSION" in codes
    assert "SECTOR_METRIC_COVERAGE_REGRESSION" in codes
    assert result["draft_publishable_count"] == 2
    assert result["acceptance"] == "ENGINEERING_FAILURES_PRESENT"


def test_universe_cardinality_and_fact_floors_are_hard_gates(tmp_path: Path) -> None:
    baseline = {
        "min_draft_publishable": 1,
        "min_extracted_plus_derived": 2,
        "min_issuer_count": 2,
        "min_downloaded_filing_count": 2,
        "min_extracted_filing_count": 2,
        "max_quarantined_extraction_timeouts": 0,
    }
    result = _evaluate(
        _acceptance_files(tmp_path, facts=[_publishable_row()], baseline=baseline)
    )
    codes = {row["code"] for row in result["universe_regressions"]}
    assert codes == {
        "ISSUER_UNIVERSE_REGRESSION",
        "DOWNLOADED_FILING_REGRESSION",
        "EXTRACTED_FILING_REGRESSION",
        "FACT_COVERAGE_REGRESSION",
    }
    assert result["acceptance"] == "ENGINEERING_FAILURES_PRESENT"


def test_live_run_cannot_masquerade_as_historical_date() -> None:
    assert_production_as_of(date(2000, 1, 1), offline=True)
    with pytest.raises(ValueError, match="Historical backfills"):
        assert_production_as_of(date(2000, 1, 1), offline=False)


def test_historical_price_resolver_never_uses_live_market_snapshot(tmp_path: Path) -> None:
    live = tmp_path / "data" / "raw" / "api" / "market_cap_2026-06-30.json"
    live.parent.mkdir(parents=True)
    live.write_text(
        json.dumps([{"symbol": "EX.N0000", "price": 999}]), encoding="utf-8"
    )
    assert strict_resolve_quarter_end_price(
        tmp_path, "EX.N0000", date(2026, 6, 30)
    ) is None

    history = (
        tmp_path
        / "data"
        / "raw"
        / "market"
        / "historical_prices"
        / "historical_2026-06-29.json"
    )
    history.parent.mkdir(parents=True)
    history.write_text(
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
    resolved = strict_resolve_quarter_end_price(
        tmp_path, "EX.N0000", date(2026, 6, 30)
    )
    assert resolved is not None
    assert str(resolved[0]) == "123.45"
    assert resolved[1] == date(2026, 6, 29)
    assert resolved[2] == "CSE_HISTORICAL"


def test_unsigned_legacy_manual_corrections_are_blocked(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "data")
    corrections = repository.root / "curated" / "manual_corrections.parquet"
    corrections.parent.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "issuer_name": "Example PLC",
                "period_end": "2026-06-30",
                "metric_code": "PAT",
                "corrected_value": "777",
            }
        ]
    ).write_parquet(corrections)
    with pytest.raises(RuntimeError, match="Unsigned manual_corrections"):
        _block_legacy_corrections(repository)


def test_revision_safe_offline_replay_uses_verified_content_addressed_file(
    tmp_path: Path,
) -> None:
    filing = Filing(
        issuer_name="Example PLC",
        symbol="EX.N0000",
        filing_id=123,
        period_end=date(2026, 6, 30),
        title="Quarter ended 30 June 2026",
        source_path="reports/example.pdf",
        source_url="https://cdn.cse.lk/reports/example.pdf",
        uploaded_at=None,
        authorized_at=None,
    )
    issuer_dir = tmp_path / "Example_PLC"
    issuer_dir.mkdir(parents=True)
    payload = b"%PDF-1.7\nverified-production-copy"
    digest = __import__("hashlib").sha256(payload).hexdigest()
    name = f"2026-06-30_123_{digest[:16]}.pdf"
    (issuer_dir / name).write_bytes(payload)
    (issuer_dir / "2026-06-30_123.current.json").write_text(
        json.dumps({"filename": name, "sha256": digest}), encoding="utf-8"
    )
    downloaded = revision_safe_download_filing(
        filing, tmp_path, offline=True
    )
    assert downloaded.sha256 == digest
    assert downloaded.local_path.name == name


class _DummyRepository:
    def __init__(self) -> None:
        self.run_id = "run-1"
        self.promoted: list[Path] = []

    def _promote(self, staging: Path) -> None:
        self.promoted.append(staging)


def test_only_acceptance_controller_can_promote_gold(tmp_path: Path) -> None:
    dummy = _DummyRepository()
    capture = ProductionRunCapture(
        repository=dummy,  # type: ignore[arg-type]
        staging=tmp_path / "staging",
        status="VALIDATION_REQUIRED",
    )
    failed = promote_staged_run(
        capture,
        {"acceptance": "ENGINEERING_FAILURES_PRESENT", "external_proof_gates": []},
        release_mode="DRAFT",
    )
    assert not failed["promoted"]
    assert not dummy.promoted

    pending_official = promote_staged_run(
        capture,
        {
            "acceptance": "ENGINEERING_PASS_EXTERNAL_PROOF_PENDING",
            "external_proof_gates": [{"code": "GOLD_SAMPLE_INCOMPLETE"}],
        },
        release_mode="OFFICIAL",
    )
    assert not pending_official["promoted"]
    assert not dummy.promoted

    accepted_draft = promote_staged_run(
        capture,
        {
            "acceptance": "ENGINEERING_PASS_EXTERNAL_PROOF_PENDING",
            "external_proof_gates": [{"code": "GOLD_SAMPLE_INCOMPLETE"}],
        },
        release_mode="DRAFT",
    )
    assert accepted_draft["promoted"]
    assert dummy.promoted == [tmp_path / "staging"]


def test_quarter_period_model_is_not_changed_by_hardening() -> None:
    periods = (
        date(2025, 12, 31),
        date(2026, 3, 31),
        date(2026, 6, 30),
        date(2026, 9, 30),
    )
    assert supporting_periods(periods) == periods
