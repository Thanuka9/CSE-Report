"""Trust-boundary invariants for human review and legacy correction inputs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl

from cse_financial_etl.contracts.release import ReviewDecision, apply_review_decisions
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.storage.repository import Repository

PERIOD = date(2026, 6, 30)


def _fact() -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=PERIOD,
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100"),
        currency="LKR",
        scale_factor=1,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Profit for the period",
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
        raw_label="Profit for the period",
        extraction_method="COMPILER_QUERY",
        semantic_model="compiler",
        semantic_confidence=1.0,
        entity_confidence=1.0,
        period_confidence=1.0,
        unit_confidence=1.0,
        column_confidence=1.0,
        validation_confidence=1.0,
        overall_certainty=0.99,
        certainty_band="HIGH",
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
    )


def _decision(*, decision: str, decided_at: str) -> ReviewDecision:
    return ReviewDecision(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=PERIOD.isoformat(),
        metric_code="PAT",
        filing_sha256="filing-sha",
        fact_fingerprint="factfp:placeholder",
        policy_version="R2-2026-09-FACTBOUND",
        reviewer_id="reviewer-1",
        decision=decision,
        decided_at=decided_at,
    )


def test_duplicate_review_decisions_do_not_use_jsonl_order_as_authority() -> None:
    fact = _fact()
    decisions = [
        _decision(decision="APPROVED", decided_at="2026-09-12T10:00:00+00:00"),
        _decision(decision="REJECTED", decided_at="2026-09-12T11:00:00+00:00"),
    ]

    updated, summary = apply_review_decisions(
        [fact],
        decisions,
        filing_sha256="filing-sha",
    )

    assert updated[0].review_status == "REVIEW"
    assert summary.approved_applied == 0
    assert summary.rejected_applied == 0
    assert summary.duplicate_decision_identities == 1


def test_legacy_unsigned_manual_correction_is_quarantined_not_applied(tmp_path) -> None:
    repo = Repository(tmp_path)
    repo.start_run("test-run", PERIOD)
    repo.fact_rows = [
        {
            "issuer_name": "Acme PLC",
            "symbol": "ACME.N0000",
            "period_end": PERIOD.isoformat(),
            "metric_code": "PAT",
            "normalized_value": "100",
            "status": "EXTRACTED",
            "review_status": "REVIEW",
            "validation_status": "PASSED",
            "missing_reason": None,
            "extraction_method": "COMPILER_QUERY",
        }
    ]
    curated = tmp_path / "curated" / "manual_corrections.parquet"
    curated.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(
        [
            {
                "issuer_name": "Acme PLC",
                "symbol": "ACME.N0000",
                "period_end": PERIOD.isoformat(),
                "metric_code": "PAT",
                "corrected_value": "999999",
            }
        ]
    ).write_parquet(curated)

    repo._apply_curated_corrections()

    assert repo.fact_rows[0]["normalized_value"] == "100"
    assert repo.fact_rows[0]["review_status"] == "REVIEW"
    assert repo.fact_rows[0]["extraction_method"] == "COMPILER_QUERY"
    assert len(repo.review_rows) == 1
    assert repo.review_rows[0]["reason"] == "UNSIGNED_CURATED_CORRECTION_QUARANTINED"
    assert repo.review_rows[0]["metric_code"] == "PAT"
