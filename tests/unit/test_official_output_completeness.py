from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.sources.cse import DownloadedFiling, Filing
from cse_financial_etl.v2.contracts.enums import PublicationStatus, ReviewStatus, ValidationStatus
from cse_financial_etl.validation.production_gates import evaluate_production_gates
from tests.unit.test_production_hardening import (
    _acceptance_files,
    _evaluate,
    _publishable_row,
)
from tests.v2.helpers import source_fact


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
    values: dict[str, object] = {
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
        "review_status": "REVIEW",
    }
    values.update(overrides)
    return ExtractedFact(**values)  # type: ignore[arg-type]


def test_draft_run_does_not_fail_official_floor_on_unreviewed_facts(
    tmp_path: Path,
) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact()])],
        coverage_baseline={"min_draft_publishable": 1, "min_official_publishable": 1},
        release_mode="DRAFT",
    )
    assert [hit.code for hit in hits] == []


def test_official_run_fails_when_draft_floor_passes_but_approvals_are_missing(
    tmp_path: Path,
) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(review_status="REVIEW")])],
        coverage_baseline={"min_draft_publishable": 1, "min_official_publishable": 1},
        release_mode="OFFICIAL",
    )
    assert "OFFICIAL_PUBLISHABLE_COVERAGE_REGRESSION" in {hit.code for hit in hits}
    assert "PUBLISHABLE_COVERAGE_REGRESSION" not in {hit.code for hit in hits}


def test_official_run_passes_when_facts_are_approved(tmp_path: Path) -> None:
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [_fact(review_status="APPROVED")])],
        coverage_baseline={"min_draft_publishable": 1, "min_official_publishable": 1},
        release_mode="OFFICIAL",
    )
    assert hits == []


def test_official_v2_release_view_gate_uses_native_review_status(tmp_path: Path) -> None:
    extracted = _fact(review_status="APPROVED")
    native = source_fact(
        fact_id="fact-1",
        issuer_id="ACM.N0000",
        review_status=ReviewStatus.REVIEW,
        publication_status=PublicationStatus.ELIGIBLE,
        validation_status=ValidationStatus.PASSED,
        period_end=date(2025, 6, 30),
        duration_months=3,
    )
    hits = evaluate_production_gates(
        [(_filing(tmp_path), [extracted])],
        coverage_baseline={"min_draft_publishable": 1, "min_official_publishable": 1},
        release_mode="OFFICIAL",
        v2_source_facts=(native,),
        v2_derived_facts=(),
    )
    assert "OFFICIAL_V2_RELEASE_VIEW_INCOMPLETE" in {hit.code for hit in hits}


def test_universe_acceptance_reports_official_count_in_draft_mode(tmp_path: Path) -> None:
    result = _evaluate(
        _acceptance_files(
            tmp_path,
            facts=[_publishable_row()],
            baseline={
                "min_draft_publishable": 1,
                "min_official_publishable": 1,
                "min_extracted_plus_derived": 1,
                "min_issuer_count": 1,
                "min_downloaded_filing_count": 1,
                "min_extracted_filing_count": 1,
                "max_quarantined_extraction_timeouts": 0,
            },
        )
    )
    assert result["draft_publishable_count"] == 1
    assert result["official_publishable_count"] == 0
    assert result["acceptance"] == "ENGINEERING_PASS"


def test_universe_acceptance_fails_official_run_on_review_only_facts(
    tmp_path: Path,
) -> None:
    result = _evaluate(
        _acceptance_files(
            tmp_path,
            facts=[_publishable_row()],
            baseline={
                "min_draft_publishable": 1,
                "min_official_publishable": 1,
                "min_extracted_plus_derived": 1,
                "min_issuer_count": 1,
                "min_downloaded_filing_count": 1,
                "min_extracted_filing_count": 1,
                "max_quarantined_extraction_timeouts": 0,
            },
            manifest_overrides={"release_mode": "OFFICIAL"},
        )
    )
    codes = {row["code"] for row in result["coverage_regressions"]}
    assert "OFFICIAL_PUBLISHABLE_COVERAGE_REGRESSION" in codes
    assert result["official_publishable_count"] == 0
    assert result["acceptance"] == "ENGINEERING_FAILURES_PRESENT"
