from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.extraction.statement_extractor import ExtractedFact
from cse_financial_etl.v2.contracts.enums import EntityScope, PublicationStatus
from cse_financial_etl.v2.production.fact_union import union_source_facts, values_agree
from cse_financial_etl.v2.production.v1_baseline import v1_extracted_to_source_fact
from tests.v2.helpers import source_fact, source_ref

VALID_SHA = "a" * 64


def _v1_row(**overrides: object) -> ExtractedFact:
    payload = dict(
        issuer_name="Acme PLC",
        symbol="ACM.N0000",
        period_end=date(2026, 6, 30),
        metric_code="PAT",
        metric_type="MONETARY_ABSOLUTE",
        raw_text="100",
        raw_value=Decimal("100"),
        normalized_value=Decimal("100000"),
        currency="LKR",
        scale_factor=1000,
        entity_scope="COMPANY",
        source_page=3,
        source_line="Profit for the period",
        unit_source_text="Rs.'000",
        confidence="HIGH",
        status="EXTRACTED",
        comparison_role="CURRENT",
        duration_months=3,
        source_bbox='{"x0":10,"y0":20,"x1":80,"y1":30}',
    )
    payload.update(overrides)
    return ExtractedFact(**payload)  # type: ignore[arg-type]


def test_adapter_maps_extracted_source_fact() -> None:
    fact = v1_extracted_to_source_fact(
        _v1_row(),
        source_sha256=VALID_SHA,
        filing_version_id="fv-1",
        issuer_id="ACM.N0000",
    )
    assert fact is not None
    assert fact.metric_code == "PAT"
    assert fact.normalized_value == Decimal("100000")
    assert fact.entity_scope is EntityScope.COMPANY
    assert fact.source_ref.bbox == (10.0, 20.0, 80.0, 30.0)
    assert "V1_BASELINE" in fact.reason_codes


def test_adapter_skips_derived_and_missing_values() -> None:
    derived = v1_extracted_to_source_fact(
        _v1_row(status="EXTRACTED_DERIVED", metric_code="DEBT_TO_EQUITY"),
        source_sha256=VALID_SHA,
        filing_version_id="fv-1",
        issuer_id="ACM.N0000",
    )
    missing = v1_extracted_to_source_fact(
        _v1_row(normalized_value=None, status="NOT_FOUND_BY_PARSER"),
        source_sha256=VALID_SHA,
        filing_version_id="fv-1",
        issuer_id="ACM.N0000",
    )
    selected = v1_extracted_to_source_fact(
        _v1_row(metric_code="EPS_SELECTED"),
        source_sha256=VALID_SHA,
        filing_version_id="fv-1",
        issuer_id="ACM.N0000",
    )
    assert derived is None
    assert missing is None
    assert selected is None


def test_union_preserves_v1_only() -> None:
    v1 = source_fact(
        fact_id="v1-pat",
        reason_codes=("V1_BASELINE",),
        source_ref=source_ref(parser_name="v1.statement_extractor", bbox=None),
    )
    merged = union_source_facts((), (v1,))
    assert len(merged) == 1
    assert merged[0].normalized_value == v1.normalized_value
    assert "V1_BASELINE_PRESERVED" in merged[0].reason_codes
    assert merged[0].publication_status is PublicationStatus.ELIGIBLE


def test_union_agree_keeps_eligible_v1_when_v2_is_withheld() -> None:
    v1 = source_fact(
        fact_id="v1",
        reason_codes=("V1_BASELINE",),
        cell_id="v1",
    )
    v2 = source_fact(
        fact_id="v2",
        publication_status=PublicationStatus.WITHHELD,
        reason_codes=("CONFLICTING_SOURCE",),
        cell_id="v2",
        source_ref=source_ref(parser_name="v2.native_pymupdf"),
    )
    merged = union_source_facts((v2,), (v1,))
    eligible = [fact for fact in merged if fact.publication_status is PublicationStatus.ELIGIBLE]
    assert len(eligible) == 1
    assert eligible[0].fact_id == "v1"
    assert "V1_V2_AGREE" in eligible[0].reason_codes


def test_union_keeps_one_when_values_agree() -> None:
    v1 = source_fact(fact_id="v1", reason_codes=("V1_BASELINE",), cell_id="v1")
    v2 = source_fact(
        fact_id="v2",
        reason_codes=("V2_NATIVE",),
        cell_id="v2",
        source_ref=source_ref(parser_name="v2.native_pymupdf"),
    )
    assert values_agree(v1.normalized_value, v2.normalized_value)
    merged = union_source_facts((v2,), (v1,))
    eligible = [fact for fact in merged if fact.publication_status is PublicationStatus.ELIGIBLE]
    assert len(eligible) == 1
    assert "V1_V2_AGREE" in eligible[0].reason_codes


def test_union_v2_replaces_only_with_stronger_evidence() -> None:
    v1 = source_fact(
        fact_id="v1",
        normalized_value=Decimal("10"),
        raw_value=Decimal("10"),
        reason_codes=("V1_BASELINE",),
        source_ref=source_ref(
            parser_name="v1.statement_extractor",
            bbox=(1.0, 2.0, 3.0, 4.0),
            raw_text=None,
        ),
        cell_id="v1",
    )
    v2 = source_fact(
        fact_id="v2",
        normalized_value=Decimal("99"),
        raw_value=Decimal("99"),
        reason_codes=("V2_NATIVE",),
        source_ref=source_ref(parser_name="v2.native_pymupdf", bbox=(1, 2, 3, 4), raw_text="99"),
        cell_id="v2",
    )
    merged = union_source_facts((v2,), (v1,))
    eligible = [fact for fact in merged if fact.publication_status is PublicationStatus.ELIGIBLE]
    withheld = [fact for fact in merged if fact.publication_status is PublicationStatus.WITHHELD]
    assert len(eligible) == 1
    assert eligible[0].normalized_value == Decimal("99")
    assert "V2_SUPERSEDES_V1" in eligible[0].reason_codes
    assert withheld and "V1_SUPERSEDED" in withheld[0].reason_codes


def test_union_quarantines_when_v1_has_no_bbox() -> None:
    v1 = source_fact(
        fact_id="v1",
        normalized_value=Decimal("10"),
        raw_value=Decimal("10"),
        reason_codes=("V1_BASELINE", "V1_BBOX_ABSENT"),
        source_ref=source_ref(parser_name="v1.statement_extractor", bbox=None, raw_text=None),
        cell_id="v1",
    )
    v2 = source_fact(
        fact_id="v2",
        normalized_value=Decimal("99"),
        raw_value=Decimal("99"),
        reason_codes=("V2_NATIVE",),
        source_ref=source_ref(parser_name="v2.native_pymupdf", bbox=(1, 2, 3, 4), raw_text="99"),
        cell_id="v2",
    )
    merged = union_source_facts((v2,), (v1,))
    assert all(fact.publication_status is PublicationStatus.WITHHELD for fact in merged)
    assert all("CONFLICT_UNRESOLVED" in fact.reason_codes for fact in merged)


def test_union_preserves_v1_on_thousand_scale_conflict() -> None:
    v1 = source_fact(
        fact_id="v1",
        normalized_value=Decimal("11263467877"),
        raw_value=Decimal("11263467877"),
        reason_codes=("V1_BASELINE",),
        cell_id="v1",
    )
    v2 = source_fact(
        fact_id="v2",
        normalized_value=Decimal("11263467877000"),
        raw_value=Decimal("11263467877000"),
        reason_codes=("V2_NATIVE",),
        source_ref=source_ref(parser_name="v2.native_pymupdf", bbox=(1, 2, 3, 4), raw_text="11,263"),
        cell_id="v2",
    )
    merged = union_source_facts((v2,), (v1,))
    eligible = [fact for fact in merged if fact.publication_status is PublicationStatus.ELIGIBLE]
    assert len(eligible) == 1
    assert eligible[0].normalized_value == Decimal("11263467877")
    assert "V1_BASELINE_PRESERVED" in eligible[0].reason_codes


def test_per_share_values_do_not_agree_within_half_unit() -> None:
    assert values_agree(Decimal("20.18"), Decimal("20.18"), metric_code="NAVPS")
    assert not values_agree(Decimal("0.40"), Decimal("0.48"), metric_code="EPS_BASIC")
    assert not values_agree(Decimal("20.18"), Decimal("20.12"), metric_code="NAVPS")
    assert values_agree(Decimal("1000000"), Decimal("1000000.4"), metric_code="PAT")


def test_union_quarantines_conflict_without_stronger_evidence() -> None:
    v1 = source_fact(
        fact_id="v1",
        normalized_value=Decimal("10"),
        raw_value=Decimal("10"),
        source_ref=source_ref(parser_name="v1.statement_extractor", bbox=(1, 2, 3, 4)),
        cell_id="v1",
    )
    v2 = source_fact(
        fact_id="v2",
        normalized_value=Decimal("99"),
        raw_value=Decimal("99"),
        source_ref=source_ref(parser_name="v2.native_pymupdf", bbox=(5, 6, 7, 8)),
        cell_id="v2",
    )
    merged = union_source_facts((v2,), (v1,))
    assert all(fact.publication_status is PublicationStatus.WITHHELD for fact in merged)
    assert all("CONFLICT_UNRESOLVED" in fact.reason_codes for fact in merged)
