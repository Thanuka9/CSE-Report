from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    PublicationStatus,
    ReleaseMode,
    ReviewStatus,
    UnitDimension,
    ValidationStatus,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact
from cse_financial_etl.v2.production.review_propagation import (
    evidence_json_for_native,
    propagate_review_status_to_native_facts,
)
from cse_financial_etl.v2.reporting.release_view import count_eligible_facts
from tests.v2.helpers import source_fact


def _extracted(**overrides: object) -> ExtractedFact:
    values: dict[str, object] = {
        "issuer_name": "Acme PLC",
        "symbol": "ACM.N0000",
        "period_end": date(2026, 6, 30),
        "metric_code": "PAT",
        "metric_type": "MONETARY_ABSOLUTE",
        "raw_text": "100",
        "raw_value": Decimal("1234000"),
        "normalized_value": Decimal("1234000"),
        "currency": "LKR",
        "scale_factor": 1,
        "entity_scope": "COMPANY",
        "source_page": 1,
        "source_line": "PAT",
        "unit_source_text": "Rs.",
        "confidence": "DETERMINISTIC",
        "status": "EXTRACTED",
        "comparison_role": "CURRENT",
        "duration_months": 3,
        "validation_status": "PASSED",
        "review_status": "APPROVED",
        "evidence_json": evidence_json_for_native("fact-1"),
    }
    values.update(overrides)
    return ExtractedFact(**values)  # type: ignore[arg-type]


def _derived(**overrides: object) -> DerivedFact:
    payload: dict[str, object] = {
        "fact_id": "derived-1",
        "issuer_id": "ACM.N0000",
        "metric_code": "NPM",
        "formula_id": "npm-1",
        "input_fact_ids": ("fact-1",),
        "normalized_value": Decimal("0.12"),
        "entity_scope": EntityScope.COMPANY,
        "period_end": date(2026, 6, 30),
        "duration_months": 3,
        "comparison_role": ComparisonRole.CURRENT,
        "unit_dimension": UnitDimension.RATIO,
        "validation_status": ValidationStatus.PASSED,
        "review_status": ReviewStatus.REVIEW,
        "publication_status": PublicationStatus.ELIGIBLE,
    }
    payload.update(overrides)
    return DerivedFact.model_validate(payload)


def test_signed_approval_propagates_by_v2_fact_id() -> None:
    native = source_fact(
        fact_id="fact-1",
        issuer_id="ACM.N0000",
        review_status=ReviewStatus.REVIEW,
        publication_status=PublicationStatus.ELIGIBLE,
        validation_status=ValidationStatus.PASSED,
    )
    source, derived = propagate_review_status_to_native_facts(
        [_extracted(review_status="APPROVED")],
        (native,),
        (),
    )
    assert source[0].review_status == ReviewStatus.APPROVED
    assert count_eligible_facts(source, derived, mode=ReleaseMode.OFFICIAL) == 1
    assert count_eligible_facts((native,), (), mode=ReleaseMode.OFFICIAL) == 0


def test_unsigned_review_is_not_copied_onto_native_facts() -> None:
    native = source_fact(
        fact_id="fact-1",
        issuer_id="ACM.N0000",
        review_status=ReviewStatus.REVIEW,
        publication_status=PublicationStatus.ELIGIBLE,
        validation_status=ValidationStatus.PASSED,
    )
    source, _derived = propagate_review_status_to_native_facts(
        [_extracted(review_status="REVIEW")],
        (native,),
        (),
    )
    assert source[0].review_status == ReviewStatus.REVIEW


def test_identity_fallback_stamps_derived_facts_without_fact_id_evidence() -> None:
    extracted = _extracted(
        metric_code="NPM",
        metric_type="RATIO",
        normalized_value=Decimal("0.12"),
        raw_value=Decimal("0.12"),
        review_status="CURATED",
        evidence_json=None,
        duration_months=3,
    )
    derived = _derived()
    _source, updated = propagate_review_status_to_native_facts([extracted], (), (derived,))
    assert updated[0].review_status == ReviewStatus.CURATED


def test_rejection_propagates_and_drops_official_eligibility() -> None:
    native = source_fact(
        fact_id="fact-1",
        issuer_id="ACM.N0000",
        review_status=ReviewStatus.REVIEW,
        publication_status=PublicationStatus.ELIGIBLE,
        validation_status=ValidationStatus.PASSED,
    )
    source, _derived = propagate_review_status_to_native_facts(
        [_extracted(review_status="REJECTED")],
        (native,),
        (),
    )
    assert source[0].review_status == ReviewStatus.REJECTED
    assert count_eligible_facts(source, (), mode=ReleaseMode.DRAFT) == 0
    assert count_eligible_facts(source, (), mode=ReleaseMode.OFFICIAL) == 0
