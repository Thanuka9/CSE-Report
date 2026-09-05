from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.extraction.statement_extractor import ExtractedFact, QuarterPrice
from cse_financial_etl.sources.cse import DownloadedFiling, Filing
from cse_financial_etl.storage.repository import Repository
from cse_financial_etl.validation.production_gates import (
    evaluate_production_gates,
    run_status_from_gates,
)


def _filing(tmp_path: Path) -> DownloadedFiling:
    filing = Filing(
        "Acme PLC",
        "ACM.N0000",
        1,
        date(2025, 6, 30),
        "Q",
        "x.pdf",
        "https://example.invalid/x.pdf",
        None,
        None,
    )
    return DownloadedFiling(filing, tmp_path / "x.pdf", "abc", 10)


def _fact(**overrides: object) -> ExtractedFact:
    values = {
        "issuer_name": "Acme PLC",
        "symbol": "ACM.N0000",
        "period_end": date(2025, 6, 30),
        "metric_code": "PAT",
        "metric_type": "MONETARY_ABSOLUTE",
        "raw_text": "100",
        "raw_value": Decimal("100"),
        "normalized_value": Decimal("100"),
        "currency": "LKR",
        "scale_factor": 1,
        "entity_scope": "COMPANY",
        "source_page": 1,
        "source_line": "PAT",
        "unit_source_text": "Rs.",
        "confidence": "HIGH",
        "status": "EXTRACTED",
        "comparison_role": "CURRENT",
        "duration_months": 3,
        "validation_status": "PASSED",
    }
    values.update(overrides)
    return ExtractedFact(**values)  # type: ignore[arg-type]


def test_gates_pass_on_clean_quarter_fact(tmp_path: Path) -> None:
    hits = evaluate_production_gates([(_filing(tmp_path), [_fact()])])
    assert hits == []
    assert run_status_from_gates(hits, has_errors=False, has_review=False) == "COMPLETED"


def test_cumulative_published_as_quarter_is_a_hard_stop(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(duration_months=6)])]
    )
    assert [hit.code for hit in hits] == ["CUMULATIVE_PUBLISHED_AS_QUARTER"]
    assert run_status_from_gates(hits, has_errors=False, has_review=False) == "VALIDATION_REQUIRED"


def test_comparative_published_as_current_is_a_hard_stop(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(comparison_role="COMPARATIVE")])]
    )
    assert [hit.code for hit in hits] == ["CURRENT_COMPARATIVE_MISMATCH"]


def test_group_where_standalone_required_is_a_hard_stop(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(entity_scope="GROUP")])],
        required_scope={"Acme PLC": "COMPANY"},
    )
    assert [hit.code for hit in hits] == ["GROUP_WHERE_STANDALONE_REQUIRED"]


def test_unit_assumed_without_evidence_is_a_hard_stop(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(unit_source_text="")])]
    )
    assert [hit.code for hit in hits] == ["UNIT_ASSUMED_WITHOUT_EVIDENCE"]


def test_unresolved_candidate_published_is_a_hard_stop(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(validation_status="FAILED")])]
    )
    assert [hit.code for hit in hits] == ["UNRESOLVED_CANDIDATE_PUBLISHED"]


def test_later_historical_price_is_a_hard_stop() -> None:
    price = QuarterPrice(
        "Acme PLC",
        "ACM.N0000",
        date(2025, 6, 30),
        Decimal("20"),
        None,
        "price_date=2025-09-04; never live snapshot after quarter end",
        "LAST_TRADE_ON_OR_BEFORE_QUARTER_END",
        "MEDIUM",
        "EXTRACTED",
    )
    hits = evaluate_production_gates([], [price])
    assert [hit.code for hit in hits] == ["HISTORICAL_PRICE_AFTER_QUARTER_END"]


def test_gold_mismatch_is_wrong_populated() -> None:
    hits = evaluate_production_gates(
        [],
        golden_validation={
            "results": [
                {
                    "status": "FAIL",
                    "issuer_name": "Acme PLC",
                    "period_end": "2025-06-30",
                    "metric_code": "PAT",
                    "expected": "100",
                    "actual": "90",
                }
            ]
        },
    )
    assert [hit.code for hit in hits] == ["GOLD_WRONG_POPULATED"]


def test_validation_required_does_not_promote_gold(tmp_path: Path) -> None:
    repository = Repository(tmp_path / "data")
    repository.start_run("run-1", date(2025, 6, 30))
    repository.finish_run("run-1", "VALIDATION_REQUIRED", {"run_id": "run-1"})
    assert not (tmp_path / "data" / "gold" / "current_financial_facts.parquet").exists()
    assert (tmp_path / "data" / "staging" / "run-1" / "manifest.json").exists()
