from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.validation.acceptance import is_publishable_fact


def _fact(**overrides: object) -> ExtractedFact:
    base = dict(
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
        source_line="PAT",
        unit_source_text="Rs.",
        confidence="HIGH",
        status="EXTRACTED",
        duration_months=3,
        validation_status="PASSED",
        review_status="APPROVED",
    )
    base.update(overrides)
    return ExtractedFact(**base)  # type: ignore[arg-type]


def test_extracted_passed_is_publishable() -> None:
    assert is_publishable_fact(_fact())


def test_failed_validation_is_not_publishable() -> None:
    assert not is_publishable_fact(_fact(validation_status="FAILED"))


def test_rejected_review_is_not_publishable() -> None:
    assert not is_publishable_fact(_fact(review_status="REJECTED"))


def test_mapping_rows_use_same_predicate() -> None:
    row = {
        "status": "EXTRACTED",
        "normalized_value": "100",
        "review_status": "APPROVED",
        "validation_status": "FAILED",
        "duration_months": 3,
        "metric_type": "MONETARY_ABSOLUTE",
    }
    assert not is_publishable_fact(row)
