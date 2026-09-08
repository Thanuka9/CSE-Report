"""Compile column schemas per stable header region (§12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from cse_financial_etl.compiler.header_tree import (
    CompiledHeaderColumn,
    HeaderCompilation,
    compile_header,
)
from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.compiler.units import UnitDeclaration
from cse_financial_etl.document.document_ir import TableIR


@dataclass(frozen=True, slots=True)
class StatementColumn:
    column_id: str
    entity: str | None
    period_end: date | None
    period_start: date | None
    temporal_type: str | None
    accounting_basis: str | None
    context_evidence_ids: tuple[str, ...]
    duration_months: int | None
    comparison_role: str | None
    currency: str | None
    scale_factor: Decimal | None
    kind: str = "VALUE"
    col_idx: int = 0
    scale_explicit: bool = False
    annotation: str | None = None
    unit_declarations: tuple[UnitDeclaration, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    conflicts: tuple[str, ...] = ()

    @property
    def is_value(self) -> bool:
        return self.kind == "VALUE"


@dataclass
class ColumnSchema:
    columns: list[StatementColumn]
    table_entity: str | None
    table_duration_months: int | None
    table_period_end: date | None
    table_units: list[UnitDeclaration]
    conflicts: list[str]
    evidence: dict[str, Any]


def compile_columns(
    table: TableIR,
    header_texts: list[str] | None = None,
    *,
    statement_type: str | None = None,
    known: KnownContext | None = None,
    currency: str | None = None,
    scale_factor: Decimal | None = None,
) -> list[StatementColumn]:
    return compile_column_schema(table, statement_type=statement_type, known=known).columns


def compile_column_schema(
    table: TableIR,
    *,
    statement_type: str | None = None,
    known: KnownContext | None = None,
) -> ColumnSchema:
    header: HeaderCompilation = compile_header(table, statement_type=statement_type, known=known)
    return ColumnSchema(
        columns=[_to_statement_column(col) for col in header.columns],
        table_entity=header.table_entity,
        table_duration_months=header.table_duration_months,
        table_period_end=header.table_period_end,
        table_units=header.table_units,
        conflicts=header.conflicts,
        evidence=header.evidence,
    )


def _to_statement_column(col: CompiledHeaderColumn) -> StatementColumn:
    return StatementColumn(
        column_id=col.column_id,
        entity=col.entity,
        period_end=col.period_end,
        period_start=col.period_start,
        temporal_type=col.temporal_type,
        accounting_basis=col.annotation,
        context_evidence_ids=col.path,
        duration_months=col.duration_months,
        comparison_role=col.comparison_role,
        currency=col.currency,
        scale_factor=col.scale_factor,
        kind=col.kind,
        col_idx=col.col_idx,
        scale_explicit=col.scale_explicit,
        annotation=col.annotation,
        unit_declarations=col.unit_declarations,
        evidence=col.evidence,
        conflicts=col.conflicts,
    )
