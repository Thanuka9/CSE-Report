from __future__ import annotations

from datetime import date
from decimal import Decimal

from cse_financial_etl.v2.contracts.enums import (
    DerivedAuditStatus,
    EntityScope,
    LineageStatus,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.facts import DerivedFact
from cse_financial_etl.v2.diagnostics.lineage import audit_derived_fact, audit_source_fact
from cse_financial_etl.v2.orchestration.filing_pipeline import run_filing_pipeline
from tests.v2.helpers import geometric_document, source_fact


def test_emitted_source_fact_has_complete_lineage() -> None:
    document = geometric_document(
        (
            ((40.0, "Company"),),
            ((40.0, "For the three months ended 30 June 2026"),),
            ((40.0, "Rs '000"),),
            ((40.0, "Profit for the period"), (300.0, "1,234")),
        )
    )
    _statements, facts, _derived, _metrics = run_filing_pipeline(
        document, issuer_id="issuer-1", expected_entity_scope=EntityScope.COMPANY
    )
    pat = next(fact for fact in facts if fact.metric_code == "PAT")
    assert audit_source_fact(pat, document=document) is LineageStatus.LINEAGE_COMPLETE


def test_normalization_error_is_detected() -> None:
    fact = source_fact()
    broken = fact.model_copy(update={"normalized_value": Decimal("1")})
    assert audit_source_fact(broken) is LineageStatus.NORMALIZATION_ERROR


def test_derived_eps_selected_recomputes() -> None:
    basic = source_fact(
        fact_id="eps-1",
        metric_code="EPS_BASIC",
        raw_value=Decimal("1.5"),
        normalized_value=Decimal("1.5"),
        source_scale=Decimal("1"),
        unit_dimension=UnitDimension.PER_SHARE,
        duration_months=3,
    )
    derived = DerivedFact(
        fact_id="eps-1-eps-selected",
        issuer_id="issuer-1",
        metric_code="EPS_SELECTED",
        formula_id="eps_selected.diluted_else_basic",
        input_fact_ids=("eps-1",),
        normalized_value=Decimal("1.5"),
        entity_scope=EntityScope.COMPANY,
        period_end=date(2026, 6, 30),
        duration_months=3,
        comparison_role=basic.comparison_role,
        unit_dimension=UnitDimension.PER_SHARE,
    )
    assert audit_derived_fact(derived, (basic,)) is DerivedAuditStatus.DERIVED_COMPLETE
