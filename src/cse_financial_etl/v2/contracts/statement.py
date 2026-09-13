"""Canonical statement structure. Column context is owned before metric matching."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cse_financial_etl.v2 import SCHEMA_VERSION
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    StatementType,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.provenance import SourceRef


class StatementColumn(BaseModel):
    """Financial context belongs to the column, with explicit source evidence.

    ``confidence`` is diagnostic only and must never replace missing evidence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    column_id: str

    entity_scope: EntityScope | None = None
    entity_evidence: tuple[SourceRef, ...] = ()

    period_end: date | None = None
    period_evidence: tuple[SourceRef, ...] = ()

    duration_months: int | None = None
    duration_evidence: tuple[SourceRef, ...] = ()

    comparison_role: ComparisonRole | None = None
    comparison_evidence: tuple[SourceRef, ...] = ()

    currency: str | None = None
    monetary_scale: Decimal | None = None
    unit_dimension: UnitDimension | None = None
    unit_evidence: tuple[SourceRef, ...] = ()

    confidence: float | None = None

    @field_validator("column_id")
    @classmethod
    def _column_id_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("column_id must be non-empty")
        return value

    @field_validator("duration_months")
    @classmethod
    def _duration_positive(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("duration_months must be positive when present")
        return value


class StatementCell(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    cell_id: str
    row_id: str
    column_id: str
    raw_text: str
    parsed_numeric_value: Decimal | None = None
    source_ref: SourceRef

    @field_validator("cell_id", "row_id", "column_id")
    @classmethod
    def _ids_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cell, row, and column ids must be non-empty")
        return value


class StatementRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    row_id: str
    raw_label: str
    normalized_label: str = ""
    cells: tuple[StatementCell, ...] = ()
    source_refs: tuple[SourceRef, ...] = ()

    @field_validator("row_id")
    @classmethod
    def _row_id_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("row_id must be non-empty")
        return value


class CanonicalStatement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["v2.0.0"] = SCHEMA_VERSION
    statement_id: str
    filing_version_id: str
    statement_type: StatementType
    pages: tuple[int, ...]
    rows: tuple[StatementRow, ...] = ()
    columns: tuple[StatementColumn, ...] = ()
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)

    @field_validator("statement_id", "filing_version_id")
    @classmethod
    def _ids_present(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("statement_id and filing_version_id must be non-empty")
        return value

    @field_validator("pages")
    @classmethod
    def _pages_positive(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value:
            raise ValueError("CanonicalStatement must record at least one page")
        if any(page < 1 for page in value):
            raise ValueError("statement page numbers must be >= 1")
        return value
