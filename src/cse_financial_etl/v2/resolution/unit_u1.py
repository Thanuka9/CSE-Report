"""U1 scoped unit resolver: V1 ROW→COLUMN→TABLE→PAGE adapted for V2 candidates.

U0 remains the default (column-level parse_unit). U1 is challenger/bake-off only
until it beats U0 without critical wrong facts.
"""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.compiler.units import (
    COUNT,
    MONETARY,
    PER_SHARE,
    PERCENT,
    SCOPE_COLUMN,
    SCOPE_PAGE,
    SCOPE_TABLE,
    UnitDeclaration,
    concept_dimension,
    label_dimension_hint,
    resolve_unit,
    row_unit_declarations,
)
from cse_financial_etl.v2.contracts.document import CanonicalDocument
from cse_financial_etl.v2.contracts.enums import ResolutionStatus, UnitDimension
from cse_financial_etl.v2.contracts.facts import FactCandidate
from cse_financial_etl.v2.contracts.statement import (
    CanonicalStatement,
    StatementColumn,
    StatementRow,
)

_DIM_TO_V2 = {
    MONETARY: UnitDimension.MONETARY,
    PER_SHARE: UnitDimension.PER_SHARE,
    COUNT: UnitDimension.COUNT,
    PERCENT: UnitDimension.PERCENTAGE,
}


def declarations_from_text(
    text: str,
    *,
    scope: str,
    owner: str,
    page: int | None = None,
) -> list[UnitDeclaration]:
    decl = UnitDeclaration.from_text(text, scope=scope, owner=owner, page=page)
    return [decl] if decl is not None else []


def column_declarations(column: StatementColumn, *, page: int | None) -> list[UnitDeclaration]:
    found: list[UnitDeclaration] = []
    for index, ref in enumerate(column.unit_evidence):
        text = ref.raw_text or ""
        if not text.strip():
            continue
        found.extend(
            declarations_from_text(
                text,
                scope=SCOPE_COLUMN,
                owner=f"col:{column.column_id}:{index}",
                page=ref.page_number,
            )
        )
    if not found and (column.currency is not None or column.monetary_scale is not None):
        found.append(
            UnitDeclaration(
                scope=SCOPE_COLUMN,
                owner=f"col:{column.column_id}:bound",
                text=f"{column.currency or ''} {column.monetary_scale or ''}".strip(),
                currency=column.currency,
                scale=column.monetary_scale,
                scale_explicit=column.monetary_scale is not None
                and column.monetary_scale != Decimal("1"),
                page=page,
            )
        )
    return found


def table_declarations(statement: CanonicalStatement) -> list[UnitDeclaration]:
    found: list[UnitDeclaration] = []
    for index, ref in enumerate(statement.source_refs[:12]):
        text = ref.raw_text or ""
        if not text.strip():
            continue
        found.extend(
            declarations_from_text(
                text,
                scope=SCOPE_TABLE,
                owner=f"table:{statement.statement_id}:{index}",
                page=ref.page_number,
            )
        )
    return found


def page_declarations(document: CanonicalDocument, page_number: int) -> list[UnitDeclaration]:
    page = next((item for item in document.pages if item.page_number == page_number), None)
    if page is None:
        return []
    found: list[UnitDeclaration] = []
    # Prefer edges of the page (headers/footers) over dense body rows.
    lines = list(page.lines)
    edge = lines[:4] + lines[-4:] if len(lines) > 8 else lines
    for index, line in enumerate(edge):
        found.extend(
            declarations_from_text(
                line.text,
                scope=SCOPE_PAGE,
                owner=f"page:{page_number}:{index}",
                page=page_number,
            )
        )
    return found


def resolve_scoped_unit(
    *,
    metric_code: str | None,
    row: StatementRow,
    column: StatementColumn,
    statement: CanonicalStatement,
    document: CanonicalDocument | None,
) -> tuple[str | None, Decimal | None, UnitDimension | None, ResolutionStatus, tuple[str, ...]]:
    """Return currency, scale, dimension, status, reasons using V1 resolve_unit."""

    page_number = None
    if row.cells:
        page_number = row.cells[0].source_ref.page_number
    elif column.unit_evidence:
        page_number = column.unit_evidence[0].page_number

    hint = label_dimension_hint(row.raw_label)
    dimension = hint or concept_dimension(metric_code)
    row_decls = row_unit_declarations(
        row.raw_label, owner=f"row:{row.row_id}", page=page_number
    )
    col_decls = column_declarations(column, page=page_number)
    tbl_decls = table_declarations(statement)
    pg_decls = (
        page_declarations(document, page_number)
        if document is not None and page_number is not None
        else []
    )
    resolution = resolve_unit(
        dimension,
        row=row_decls,
        column=col_decls,
        table=tbl_decls,
        page=pg_decls,
    )
    v2_dim = _DIM_TO_V2.get(resolution.dimension)
    if resolution.status != "RESOLVED":
        return (
            None,
            None,
            v2_dim,
            ResolutionStatus.UNRESOLVED,
            tuple(resolution.reasons),
        )
    return (
        resolution.currency,
        resolution.scale,
        v2_dim,
        ResolutionStatus.RESOLVED,
        tuple(resolution.reasons),
    )


def apply_u1_unit(
    candidate: FactCandidate,
    *,
    row: StatementRow,
    column: StatementColumn,
    statement: CanonicalStatement,
    document: CanonicalDocument | None,
) -> FactCandidate:
    metric = None if candidate.concept is None else candidate.concept.metric_code
    currency, scale, dimension, status, reasons = resolve_scoped_unit(
        metric_code=metric,
        row=row,
        column=column,
        statement=statement,
        document=document,
    )
    updated_reasons = tuple(
        code for code in candidate.reason_codes if code != "UNIT_NOT_RESOLVED"
    )
    if status is ResolutionStatus.UNRESOLVED:
        updated_reasons = (*updated_reasons, "UNIT_NOT_RESOLVED", *reasons[:3])
    return candidate.model_copy(
        update={
            "currency": currency,
            "monetary_scale": scale,
            "unit_dimension": dimension,
            "unit_status": status,
            "reason_codes": updated_reasons,
        }
    )


def unit_u1_census(candidates: tuple[FactCandidate, ...]) -> dict[str, int]:
    unresolved = sum(1 for item in candidates if item.unit_status is ResolutionStatus.UNRESOLVED)
    per_share = sum(
        1 for item in candidates if item.unit_dimension is UnitDimension.PER_SHARE
    )
    inherited_thousands = sum(
        1
        for item in candidates
        if item.unit_dimension is UnitDimension.PER_SHARE
        and item.monetary_scale is not None
        and item.monetary_scale >= Decimal("1000")
    )
    return {
        "candidates": len(candidates),
        "unit_unresolved": unresolved,
        "per_share_candidates": per_share,
        "per_share_with_thousands_scale": inherited_thousands,
    }


__all__ = [
    "apply_u1_unit",
    "resolve_scoped_unit",
    "unit_u1_census",
]
