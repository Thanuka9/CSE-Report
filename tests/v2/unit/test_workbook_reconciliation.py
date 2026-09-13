from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope
from cse_financial_etl.v2.exceptions import (
    ReleaseContextRequiredError,
    WorkbookReconciliationFailed,
)
from cse_financial_etl.v2.reporting.reconciliation import (
    DisplayedWorkbookCell,
    EligibleReleaseFact,
    PivotFact,
    reconcile_workbook,
)
from tests.v2.helpers import release_context


def _eligible() -> EligibleReleaseFact:
    return EligibleReleaseFact(
        fact_id="fact-1",
        issuer_id="issuer-1",
        metric_code="PAT",
        period_end=date(2026, 6, 30),
        duration_months=3,
        comparison_role=ComparisonRole.CURRENT,
        entity_scope=EntityScope.COMPANY,
        normalized_value=Decimal("1234"),
    )


def test_numeric_cells_must_reconcile_to_eligible_facts() -> None:
    fact = _eligible()
    report = reconcile_workbook(
        release=release_context(),
        eligible=(fact,),
        pivot=(
            PivotFact(
                fact_id=fact.fact_id,
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                normalized_value=fact.normalized_value,
            ),
        ),
        displayed=(
            DisplayedWorkbookCell(
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                value=fact.normalized_value,
                sheet="Snapshot",
                cell_address="E5",
            ),
        ),
    )
    assert report.ok
    report.raise_if_failed()


def test_status_strings_in_financial_cells_fail_reconciliation() -> None:
    fact = _eligible()
    report = reconcile_workbook(
        release=release_context(),
        eligible=(fact,),
        pivot=(
            PivotFact(
                fact_id=fact.fact_id,
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                normalized_value=fact.normalized_value,
            ),
        ),
        displayed=(
            DisplayedWorkbookCell(
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                value=None,
                raw_written="ENTITY_NOT_RESOLVED",
                sheet="Snapshot",
                cell_address="E5",
            ),
        ),
    )
    assert not report.ok
    assert any(item.kind == "STATUS_IN_NUMERIC_CELL" for item in report.mismatches)
    with pytest.raises(WorkbookReconciliationFailed, match="WORKBOOK_RECONCILIATION_FAILED"):
        report.raise_if_failed()


def test_value_mismatch_fails_closed() -> None:
    fact = _eligible()
    report = reconcile_workbook(
        release=release_context(),
        eligible=(fact,),
        pivot=(
            PivotFact(
                fact_id=fact.fact_id,
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                normalized_value=Decimal("999"),
            ),
        ),
        displayed=(
            DisplayedWorkbookCell(
                issuer_id=fact.issuer_id,
                metric_code=fact.metric_code,
                period_end=fact.period_end,
                value=Decimal("999"),
                sheet="Snapshot",
                cell_address="E5",
            ),
        ),
    )
    assert any(item.kind == "VALUE_MISMATCH" for item in report.mismatches)


def test_reconciliation_requires_release_context() -> None:
    with pytest.raises(ReleaseContextRequiredError):
        reconcile_workbook(release=None, eligible=(), pivot=(), displayed=())
