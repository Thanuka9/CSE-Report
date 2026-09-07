"""Compile column schemas per stable header region (§12)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cse_financial_etl.compiler.header_tree import CompiledHeaderColumn, compile_header_tree
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


def compile_columns(
    table: TableIR,
    header_texts: list[str],
    *,
    currency: str | None = "LKR",
    scale_factor: Decimal | None = None,
) -> list[StatementColumn]:
    compiled = compile_header_tree(table, header_texts)
    return [_to_statement_column(col, currency, scale_factor) for col in compiled]


def _to_statement_column(
    col: CompiledHeaderColumn,
    currency: str | None,
    scale_factor: Decimal | None,
) -> StatementColumn:
    return StatementColumn(
        column_id=col.column_id,
        entity=col.entity,
        period_end=col.period_end,
        period_start=None,
        temporal_type="duration" if col.duration_months else "instant",
        accounting_basis=None,
        context_evidence_ids=col.path,
        duration_months=col.duration_months,
        comparison_role=col.comparison_role,
        currency=currency,
        scale_factor=scale_factor,
    )
