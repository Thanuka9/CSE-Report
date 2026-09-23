from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import ReviewStatus, ValidationStatus
from cse_financial_etl.v2.production.adapter import synchronize_native_governance
from tests.v2.helpers import source_fact


def _row(*, value: Decimal = Decimal("1234000"), review: str = "APPROVED") -> ExtractedFact:
    return ExtractedFact(
        issuer_name="Example PLC",
        symbol="EX.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text="1,234",
        raw_value=Decimal("1234"),
        normalized_value=value,
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=1,
        source_line="Profit for the period 1,234",
        unit_source_text="Rs. '000",
        confidence="DETERMINISTIC",
        status="EXTRACTED",
        validation_status="PASSED",
        review_status=review,
        comparison_role="CURRENT",
        duration_months=3,
    )


def test_signed_review_state_reaches_native_source_fact() -> None:
    native = source_fact(issuer_id="EX.N0000")
    source, derived = synchronize_native_governance((native,), (), [_row()])
    assert not derived
    assert source[0].validation_status == ValidationStatus.PASSED
    assert source[0].review_status == ReviewStatus.APPROVED


def test_value_mismatch_does_not_propagate_review_state() -> None:
    native = source_fact(issuer_id="EX.N0000")
    source, _derived = synchronize_native_governance(
        (native,),
        (),
        [_row(value=Decimal("999"))],
    )
    assert source[0].review_status == ReviewStatus.REVIEW


def test_conflicting_governance_rows_fail_closed() -> None:
    native = source_fact(issuer_id="EX.N0000")
    source, _derived = synchronize_native_governance(
        (native,),
        (),
        [_row(review="APPROVED"), _row(review="REJECTED")],
    )
    assert source[0].review_status == ReviewStatus.REVIEW
