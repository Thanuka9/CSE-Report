"""Workbook reconciliation harness. Excel is a renderer, not a publication engine."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope
from cse_financial_etl.v2.contracts.release import ReleaseContext, require_release_context
from cse_financial_etl.v2.exceptions import WorkbookReconciliationFailed

FORBIDDEN_NUMERIC_CELL_STRINGS: frozenset[str] = frozenset(
    {
        "ENTITY_NOT_RESOLVED",
        "REVIEW_REQUIRED",
        "PERIOD_NOT_RESOLVED",
        "UNIT_NOT_RESOLVED",
        "DURATION_NOT_RESOLVED",
        "WITHHELD",
        "FAILED",
        "MISSING",
        "N/A",
        "NA",
        "NONE",
    }
)


class EligibleReleaseFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    fact_id: str
    issuer_id: str
    metric_code: str
    period_end: date
    duration_months: int | None = None
    comparison_role: ComparisonRole
    entity_scope: EntityScope
    normalized_value: Decimal


class PivotFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    fact_id: str
    issuer_id: str
    metric_code: str
    period_end: date
    normalized_value: Decimal
    exclusion_reason: str | None = None


class DisplayedWorkbookCell(BaseModel):
    """A financial cell as actually written to the workbook."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    issuer_id: str
    metric_code: str
    period_end: date
    value: Decimal | None = None
    raw_written: object | None = None
    sheet: str
    cell_address: str

    @field_validator("value")
    @classmethod
    def _numeric_or_blank(cls, value: Decimal | None) -> Decimal | None:
        return value


class ReconciliationMismatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    identity: str
    detail: str


class WorkbookReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    release: ReleaseContext
    eligible_count: int
    pivot_count: int
    expected_display_count: int
    actual_numeric_cell_count: int
    mismatches: tuple[ReconciliationMismatch, ...]

    @property
    def ok(self) -> bool:
        return not self.mismatches

    def raise_if_failed(self) -> None:
        if self.ok:
            return
        details = "; ".join(
            f"{item.kind}:{item.identity}:{item.detail}" for item in self.mismatches
        )
        raise WorkbookReconciliationFailed(f"{WorkbookReconciliationFailed.reason_code}: {details}")


def _identity(issuer_id: str, metric_code: str, period_end: date) -> str:
    return f"{issuer_id}|{metric_code}|{period_end.isoformat()}"


def _status_string(value: object) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace(" ", "_").upper()
    if normalized in FORBIDDEN_NUMERIC_CELL_STRINGS:
        return normalized
    if normalized.isidentifier() and normalized.endswith("_NOT_RESOLVED"):
        return normalized
    if normalized in {"REVIEW_REQUIRED", "VALIDATION_FAILED"}:
        return normalized
    return None


def reconcile_workbook(
    *,
    release: ReleaseContext | None,
    eligible: tuple[EligibleReleaseFact, ...],
    pivot: tuple[PivotFact, ...],
    displayed: tuple[DisplayedWorkbookCell, ...],
) -> WorkbookReconciliationReport:
    """Reconcile eligible facts → pivot selection → displayed numeric cells.

    Status/reason strings belong on dedicated sheets, never in financial cells.
    """

    context = require_release_context(release)
    mismatches: list[ReconciliationMismatch] = []

    eligible_ids = {
        _identity(fact.issuer_id, fact.metric_code, fact.period_end): fact for fact in eligible
    }
    if len(eligible_ids) != len(eligible):
        mismatches.append(
            ReconciliationMismatch(
                kind="DUPLICATE_ELIGIBLE",
                identity="eligible",
                detail="eligible release facts are not unique by issuer/metric/period",
            )
        )

    pivot_included = [item for item in pivot if not item.exclusion_reason]
    pivot_ids = {
        _identity(item.issuer_id, item.metric_code, item.period_end): item
        for item in pivot_included
    }
    if len(pivot_ids) != len(pivot_included):
        mismatches.append(
            ReconciliationMismatch(
                kind="DUPLICATE_PIVOT",
                identity="pivot",
                detail="pivot facts are not unique by issuer/metric/period",
            )
        )
    excluded = {
        _identity(item.issuer_id, item.metric_code, item.period_end): item
        for item in pivot
        if item.exclusion_reason
    }

    for identity, fact in eligible_ids.items():
        if identity in excluded:
            continue
        selected = pivot_ids.get(identity)
        if selected is None:
            mismatches.append(
                ReconciliationMismatch(
                    kind="MISSING_FROM_PIVOT",
                    identity=identity,
                    detail="eligible fact was not selected for the pivot and has no exclusion reason",
                )
            )
            continue
        if selected.normalized_value != fact.normalized_value:
            mismatches.append(
                ReconciliationMismatch(
                    kind="VALUE_MISMATCH",
                    identity=identity,
                    detail="pivot value differs from eligible release fact",
                )
            )

    for identity, _item in pivot_ids.items():
        if identity not in eligible_ids:
            mismatches.append(
                ReconciliationMismatch(
                    kind="UNEXPECTED_PIVOT",
                    identity=identity,
                    detail="pivot fact is not in the eligible release set",
                )
            )

    displayed_ids: dict[str, DisplayedWorkbookCell] = {}
    for cell in displayed:
        identity = _identity(cell.issuer_id, cell.metric_code, cell.period_end)
        if identity in displayed_ids:
            mismatches.append(
                ReconciliationMismatch(
                    kind="DUPLICATE_DISPLAY",
                    identity=identity,
                    detail=f"duplicated workbook cell {cell.sheet}!{cell.cell_address}",
                )
            )
            continue
        displayed_ids[identity] = cell
        status = _status_string(cell.raw_written if cell.raw_written is not None else cell.value)
        if status is not None:
            mismatches.append(
                ReconciliationMismatch(
                    kind="STATUS_IN_NUMERIC_CELL",
                    identity=identity,
                    detail=f"financial cell contains {status}",
                )
            )
            continue
        if cell.value is None:
            continue
        selected = pivot_ids.get(identity)
        if selected is None:
            mismatches.append(
                ReconciliationMismatch(
                    kind="UNEXPECTED_CELL",
                    identity=identity,
                    detail="numeric workbook cell has no matching pivot fact",
                )
            )
        elif cell.value != selected.normalized_value:
            mismatches.append(
                ReconciliationMismatch(
                    kind="VALUE_MISMATCH",
                    identity=identity,
                    detail="workbook numeric cell differs from pivot fact",
                )
            )

    for identity in pivot_ids:
        matched = displayed_ids.get(identity)
        if matched is None or matched.value is None:
            mismatches.append(
                ReconciliationMismatch(
                    kind="MISSING_NUMERIC_CELL",
                    identity=identity,
                    detail="pivot fact has no numeric workbook cell",
                )
            )

    for identity, item in excluded.items():
        matched = displayed_ids.get(identity)
        if matched is not None and matched.value is not None:
            mismatches.append(
                ReconciliationMismatch(
                    kind="EXCLUDED_FACT_DISPLAYED",
                    identity=identity,
                    detail=f"excluded ({item.exclusion_reason}) but displayed numerically",
                )
            )

    numeric_cells = tuple(cell for cell in displayed if cell.value is not None)
    return WorkbookReconciliationReport(
        release=context,
        eligible_count=len(eligible),
        pivot_count=len(pivot_included),
        expected_display_count=len(pivot_ids),
        actual_numeric_cell_count=len(numeric_cells),
        mismatches=tuple(mismatches),
    )
