from __future__ import annotations

from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from cse_financial_etl.v2.contracts.enums import EntityScope, PublicationStatus, ValidationStatus
from cse_financial_etl.v2.contracts.facts import SourceFact
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.validation.accounting import validate_source_facts
from tests.v2.helpers import VALID_SHA, source_fact, source_ref

hex_sha = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)


@given(
    st.decimals(
        min_value="0.01", max_value="1000000", places=4, allow_nan=False, allow_infinity=False
    )
)
def test_source_fact_decimal_roundtrip_is_exact(value: Decimal) -> None:
    fact = source_fact(raw_value=value, normalized_value=value)
    restored = SourceFact.model_validate_json(fact.model_dump_json())
    assert restored.raw_value == value
    assert restored.normalized_value == value
    assert restored.source_ref.source_sha256 == VALID_SHA


@given(hex_sha)
def test_source_ref_accepts_only_complete_sha(digest: str) -> None:
    ref = source_ref(source_sha256=digest)
    assert ref.source_sha256 == digest
    dumped = SourceRef.model_validate(ref.model_dump())
    assert dumped.source_sha256 == digest


def test_source_fact_cannot_exist_without_provenance() -> None:
    payload = source_fact().model_dump()
    payload["source_ref"] = None
    try:
        SourceFact.model_validate(payload)
    except ValidationError:
        return
    raise AssertionError("SourceFact accepted a missing source_ref")


def test_group_enum_cannot_equal_company() -> None:
    assert EntityScope.GROUP.value != EntityScope.COMPANY.value
    fact = source_fact(entity_scope=EntityScope.GROUP, period_end=date(2026, 6, 30))
    assert fact.entity_scope is not EntityScope.COMPANY


@given(st.sampled_from([6, 9, 12]))
def test_non_quarter_flow_cannot_stay_eligible(duration: int) -> None:
    fact = source_fact(duration_months=duration)
    validated = validate_source_facts((fact,))[0]
    assert validated.duration_months == duration
    assert validated.publication_status is PublicationStatus.WITHHELD
    assert validated.validation_status is ValidationStatus.FAILED
