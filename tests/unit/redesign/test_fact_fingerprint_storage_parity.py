from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.contracts.release import fact_fingerprint
from cse_financial_etl.extraction.statement_extractor import ExtractedFact


def test_fact_fingerprint_matches_serialized_fact_form() -> None:
    fact = ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=4,
        source_line="Profit for the period",
        unit_source_text="LKR '000",
        confidence="HIGH",
        status="EXTRACTED",
        raw_label="Profit for the period",
        source_bbox="(1,2,3,4)",
        extraction_method="COMPILER_QUERY",
        semantic_model="compiler",
        semantic_confidence=1.0,
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
        evidence_json='{"extraction_origin":"compiler_geometry","source_evidence":{"page":4,"label":"Profit for the period"},"compiler_report_summary":{"run_id":"ignored"}}',
    )
    serialized = fact.as_json()
    assert fact_fingerprint(fact) == fact_fingerprint(serialized)


def test_run_level_diagnostics_do_not_invalidate_same_fact() -> None:
    base = ExtractedFact(
        issuer_name="Acme PLC",
        symbol="ACME.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=4,
        source_line="Profit for the period",
        unit_source_text="LKR '000",
        confidence="HIGH",
        status="EXTRACTED",
        raw_label="Profit for the period",
        extraction_method="COMPILER_QUERY",
        semantic_model="compiler",
        comparison_role="CURRENT",
        duration_months=3,
        validation_status="PASSED",
        review_status="REVIEW",
        evidence_json='{"extraction_origin":"compiler_geometry","source_evidence":{"page":4,"label":"Profit for the period"},"compiler_report_summary":{"run_id":"one"}}',
    )
    rerun = ExtractedFact(**{**base.__dict__, "evidence_json": '{"extraction_origin":"compiler_geometry","source_evidence":{"page":4,"label":"Profit for the period"},"compiler_report_summary":{"run_id":"two"}}'})
    assert fact_fingerprint(base) == fact_fingerprint(rerun)
