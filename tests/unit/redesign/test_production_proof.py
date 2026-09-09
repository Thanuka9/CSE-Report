from __future__ import annotations

import csv
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from cse_financial_etl.contracts.release import (
    apply_review_decisions,
    make_decision,
    sign_decision,
    verify_decision_signature,
)
from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.adjudication import (
    prepare_adjudication_packet,
    validate_adjudication_packet,
)
from cse_financial_etl.validation.calibration import calibration_from_results


def _fact() -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
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
        duration_months=3,
        comparison_role="CURRENT",
        validation_status="PASSED",
        review_status="REVIEW",
    )


def test_calibration_is_fail_closed_until_manual_sample_is_large_enough() -> None:
    small = [
        {"verification_status": "MANUAL_QA", "status": "PASS", "overall_certainty": 0.95}
        for _ in range(20)
    ]
    result = calibration_from_results(small)
    assert result["status"] == "INSUFFICIENT_MANUAL_SAMPLE"
    assert result["sample_size"] == 20


def test_calibration_reports_brier_and_ece_on_sufficient_manual_truth() -> None:
    rows = []
    for _ in range(50):
        rows.append({"verification_status": "MANUAL_QA", "status": "PASS", "overall_certainty": 0.95})
    for _ in range(50):
        rows.append({"verification_status": "MANUAL_QA", "status": "FAIL", "overall_certainty": 0.55})
    result = calibration_from_results(rows)
    assert result["status"] == "CALIBRATED"
    assert result["sample_size"] == 100
    assert result["brier_score"] is not None
    assert result["expected_calibration_error"] is not None


def test_unsigned_review_name_cannot_authenticate_official_decision() -> None:
    fact = _fact()
    decision = make_decision(
        issuer_name=fact.issuer_name,
        symbol=fact.symbol,
        period_end=fact.period_end.isoformat(),
        metric_code=fact.metric_code,
        filing_sha256="abc123",
        reviewer_id="reviewer@example.org",
        decision="APPROVED",
    )
    updated, summary = apply_review_decisions([fact], [decision], filing_sha256="abc123")
    assert updated[0].review_status == "REVIEW"
    assert summary.unauthenticated == 1


def test_signed_review_decision_applies_and_tampering_fails(monkeypatch) -> None:
    fact = _fact()
    unsigned = make_decision(
        issuer_name=fact.issuer_name,
        symbol=fact.symbol,
        period_end=fact.period_end.isoformat(),
        metric_code=fact.metric_code,
        filing_sha256="abc123",
        reviewer_id="reviewer@example.org",
        decision="APPROVED",
    )
    signed = sign_decision(unsigned, secret="institution-secret", key_id="BSD-REVIEW-1")
    monkeypatch.setenv("CSE_REVIEW_KEY_BSD_REVIEW_1", "institution-secret")
    assert verify_decision_signature(signed) == (True, "AUTHENTICATED")
    updated, summary = apply_review_decisions([fact], [signed], filing_sha256="abc123")
    assert updated[0].review_status == "APPROVED"
    assert summary.approved_applied == 1

    tampered = replace(signed, note="changed after signature")
    assert verify_decision_signature(tampered)[0] is False


def test_adjudication_packet_requires_100_explicit_human_issuers(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    facts = outputs / "normalized_facts_2026-09-09.csv"
    headers = [
        "issuer_name", "symbol", "period_end", "metric_code", "normalized_value", "status",
        "entity_scope", "duration_months", "comparison_role", "currency", "scale_factor",
        "source_page", "overall_certainty", "filing_sha256", "source_url", "local_path",
    ]
    with facts.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for index in range(100):
            writer.writerow({
                "issuer_name": f"Issuer {index:03d} PLC",
                "symbol": f"I{index:03d}.N0000",
                "period_end": "2026-06-30",
                "metric_code": "PAT",
                "normalized_value": str(index + 1),
                "status": "EXTRACTED",
                "entity_scope": "COMPANY",
                "duration_months": "3",
                "comparison_role": "CURRENT",
                "currency": "LKR",
                "scale_factor": "1000",
                "source_page": "1",
                "overall_certainty": "0.9",
                "filing_sha256": f"sha-{index}",
                "source_url": f"https://example.test/{index}.pdf",
                "local_path": f"data/{index}.pdf",
            })

    manifest = prepare_adjudication_packet(tmp_path, date(2026, 9, 9), target_issuers=100)
    assert manifest["issuer_count"] == 100
    packet = Path(manifest["packet"])
    assert validate_adjudication_packet(packet)["status"] == "INCOMPLETE"

    rows = []
    with packet.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        assert fieldnames is not None
        for row in reader:
            row.update({
                "human_value": row["machine_value"],
                "human_entity_scope": "COMPANY",
                "human_duration_months": "3",
                "human_comparison_role": "CURRENT",
                "human_unit": "LKR",
                "human_scale_factor": "1000",
                "human_source_page": "1",
                "human_verdict": "PASS",
                "reviewer_id": "human-reviewer",
                "reviewed_at": "2026-09-09T00:00:00Z",
            })
            rows.append(row)
    with packet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    validated = validate_adjudication_packet(packet)
    assert validated["status"] == "READY_FOR_MANUAL_QA_IMPORT"
    assert validated["completed_issuer_count"] == 100
