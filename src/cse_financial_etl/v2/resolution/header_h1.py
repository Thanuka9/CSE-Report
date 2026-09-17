"""H1 header engine: V1 header_tree geometry adapted onto V2 CanonicalStatement.

H0 remains the production default. H1 is challenger-only for bake-off.
Does not copy query-target metadata. Rejects table-title/caption silent fills.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Literal

from cse_financial_etl.compiler.header_tree import compile_header
from cse_financial_etl.compiler.structure_normalizer import normalize_date
from cse_financial_etl.document.document_ir import (
    BBox,
    HeaderPhraseIR,
    TableCellIR,
    TableColumnIR,
    TableIR,
)
from cse_financial_etl.document.table_reconstructor import _phrase_kind
from cse_financial_etl.v2.contracts.document import CanonicalDocument, CanonicalLine, CanonicalToken
from cse_financial_etl.v2.contracts.enums import (
    ComparisonRole,
    EntityScope,
    StatementType,
    UnitDimension,
)
from cse_financial_etl.v2.contracts.provenance import SourceRef
from cse_financial_etl.v2.contracts.statement import CanonicalStatement, StatementColumn
from cse_financial_etl.v2.resolution.column_context import (
    _fail_closed_partial_monetary_columns,
    context_blob,
    parse_unit,
)
from cse_financial_etl.v2.statements.detector import StatementRegion, detect_statement_regions
from cse_financial_etl.v2.statements.numeric import split_label_and_values

_SILENT_SOURCES = frozenset({"table_title", "table_caption"})

_STATEMENT_TYPE_TO_V1 = {
    StatementType.INCOME_STATEMENT: "PROFIT_LOSS",
    StatementType.BALANCE_SHEET: "FINANCIAL_POSITION",
    StatementType.CASH_FLOW: "CASH_FLOW",
    StatementType.CHANGES_IN_EQUITY: "CHANGES_IN_EQUITY",
    StatementType.EPS_NOTE: "EPS_NOTE",
    StatementType.OTHER_FINANCIAL_STATEMENT: "OTHER",
}

_ENTITY_MAP = {
    "COMPANY": EntityScope.COMPANY,
    "GROUP": EntityScope.GROUP,
    "BANK": EntityScope.BANK,
    "CONSOLIDATED": EntityScope.CONSOLIDATED,
    "SEPARATE": EntityScope.SEPARATE,
}


def bind_column_context_h1(
    document: CanonicalDocument,
    statement: CanonicalStatement,
    *,
    expected_entity_scope: EntityScope | None = None,
    target_period_end: date | None = None,
    partial_monetary: Literal["cascade", "per_column"] = "cascade",
) -> CanonicalStatement:
    """Fill column context via V1 compile_header geometry mapped into V2 columns."""

    del expected_entity_scope, target_period_end
    regions = detect_statement_regions(document)
    region = next((item for item in regions if item.region_id == statement.statement_id), None)
    evidence = statement.source_refs[:1]
    blob = context_blob(document, region) if region is not None else ""
    blob = blob or " ".join(ref.raw_text or "" for ref in statement.source_refs)

    table = _table_ir_from_statement(document, statement, region)
    if table is None or len([c for c in table.columns if c.kind == "VALUE"]) == 0:
        # Fall back structurally empty — leave unresolved rather than inventing H0 fills.
        return statement.model_copy(
            update={
                "columns": tuple(StatementColumn(column_id=column.column_id) for column in statement.columns)
            }
        )

    v1_type = _STATEMENT_TYPE_TO_V1.get(statement.statement_type, "OTHER")
    compilation = compile_header(table, statement_type=v1_type, known=None)
    value_cols = [col for col in compilation.columns if col.kind == "VALUE"]
    if len(value_cols) != len(statement.columns):
        # Column cardinality mismatch — do not force-align; leave unresolved.
        return statement.model_copy(
            update={
                "columns": tuple(StatementColumn(column_id=column.column_id) for column in statement.columns)
            }
        )

    default_unit = parse_unit(blob)
    columns: list[StatementColumn] = []
    for statement_column, compiled in zip(statement.columns, value_cols, strict=True):
        columns.append(
            _map_compiled_column(
                statement_column,
                compiled,
                evidence=evidence,
                default_unit=default_unit,
                statement_type=statement.statement_type,
            )
        )

    if partial_monetary == "cascade":
        columns = _fail_closed_partial_monetary_columns(statement, columns)
    return statement.model_copy(update={"columns": tuple(columns)})


def _map_compiled_column(
    statement_column: StatementColumn,
    compiled: object,
    *,
    evidence: tuple[SourceRef, ...],
    default_unit: tuple[str | None, Decimal | None, UnitDimension | None],
    statement_type: StatementType,
) -> StatementColumn:
    entity_raw = getattr(compiled, "entity", None)
    entity_ev = getattr(compiled, "evidence", {}) or {}
    entity_source = (entity_ev.get("entity") or {}).get("source")
    entity = None
    if entity_raw is not None and entity_source not in _SILENT_SOURCES:
        entity = _ENTITY_MAP.get(str(entity_raw).upper())

    period_end = getattr(compiled, "period_end", None)
    period_source = (entity_ev.get("period_end") or entity_ev.get("period") or {}).get("source")
    if period_source in _SILENT_SOURCES:
        period_end = None
    # Full-width duration banners are assigned to every value column by V1 block
    # geometry, but V1 only embeds dates when the phrase is right-aligned to the
    # column. On V2 reconstructed statements those banners are often left-anchored;
    # if the bound duration text itself carries a calendar date, use it.
    if period_end is None:
        duration_ev = entity_ev.get("duration") or {}
        if duration_ev.get("source") not in _SILENT_SOURCES:
            embedded = normalize_date(str(duration_ev.get("text") or ""))
            if embedded is not None:
                period_end = embedded

    duration = getattr(compiled, "duration_months", None)
    duration_source = (entity_ev.get("duration") or {}).get("source")
    if duration_source in _SILENT_SOURCES:
        duration = None
    if statement_type is StatementType.BALANCE_SHEET:
        duration = None

    role_raw = getattr(compiled, "comparison_role", None)
    role = None
    if role_raw in {"CURRENT", "COMPARATIVE"}:
        role = ComparisonRole(role_raw)

    currency = getattr(compiled, "currency", None)
    scale = getattr(compiled, "scale_factor", None)
    unit_dimension: UnitDimension | None = None
    if currency is not None or scale is not None:
        unit_dimension = UnitDimension.MONETARY
    if statement_type is StatementType.EPS_NOTE:
        unit_dimension = UnitDimension.PER_SHARE
        currency = currency or "LKR"
        scale = Decimal("1") if scale is None else scale
    if unit_dimension is None and default_unit[2] is not None:
        currency, scale, unit_dimension = default_unit

    return StatementColumn(
        column_id=statement_column.column_id,
        entity_scope=entity,
        entity_evidence=evidence if entity is not None else (),
        period_end=period_end,
        period_evidence=evidence if period_end is not None else (),
        duration_months=duration,
        duration_evidence=evidence if duration is not None else (),
        comparison_role=role,
        comparison_evidence=evidence if role is not None else (),
        currency=currency,
        monetary_scale=scale,
        unit_dimension=unit_dimension,
        unit_evidence=evidence if unit_dimension is not None else (),
    )


def _table_ir_from_statement(
    document: CanonicalDocument,
    statement: CanonicalStatement,
    region: StatementRegion | None,
) -> TableIR | None:
    page_number = region.page_start if region is not None else 1
    value_columns = _value_column_geometry(statement)
    if not value_columns:
        return None

    label_col = TableColumnIR(col_idx=0, x_center=40.0, x_min=0.0, x_max=120.0, kind="LABEL")
    columns = (label_col, *value_columns)

    header_lines = _header_lines(document, region)
    phrases: list[HeaderPhraseIR] = []
    for row_idx, line in enumerate(header_lines):
        for text, bbox in _line_phrases(line):
            phrases.append(
                HeaderPhraseIR(row_idx=row_idx, text=text, bbox=bbox, kind=_phrase_kind(text))
            )

    cells: list[TableCellIR] = []
    for row_index, row in enumerate(statement.rows):
        for cell in row.cells:
            col_idx = _column_index(statement, cell.column_id)
            if col_idx is None or cell.source_ref.bbox is None:
                continue
            x0, y0, x1, y1 = cell.source_ref.bbox
            cells.append(
                TableCellIR(
                    row_idx=row_index,
                    col_idx=col_idx + 1,  # 0 is label
                    raw_text=cell.raw_text,
                    bbox=BBox(x0, y0, x1, y1),
                )
            )

    title_texts: tuple[str, ...] = ()
    if region is not None and document.pages:
        pages = {page.page_number: page for page in document.pages}
        page = pages.get(region.page_start)
        if page is not None and page.lines:
            title_texts = (page.lines[0].text,)

    xs = [col.x_min for col in value_columns] + [col.x_max for col in value_columns]
    ys = [0.0, 40.0]
    if cells:
        ys = [min(cell.bbox.y0 for cell in cells) - 40.0, max(cell.bbox.y1 for cell in cells) + 10.0]
    if phrases:
        ys[0] = min(ys[0], min(p.bbox.y0 for p in phrases) - 4.0)
    table_bbox = BBox(min(xs + [0.0]), ys[0], max(xs + [400.0]), ys[1])

    return TableIR(
        page_number=page_number,
        bbox=table_bbox,
        cells=tuple(cells),
        columns=columns,
        header_phrases=tuple(phrases),
        title_texts=title_texts,
        caption_phrases=(),
        source_method="v2_h1_adapter",
    )


def _value_column_geometry(statement: CanonicalStatement) -> tuple[TableColumnIR, ...]:
    built: list[TableColumnIR] = []
    for index, column in enumerate(statement.columns):
        xs: list[float] = []
        for row in statement.rows:
            for cell in row.cells:
                if cell.column_id != column.column_id or cell.source_ref.bbox is None:
                    continue
                x0, _y0, x1, _y1 = cell.source_ref.bbox
                xs.append((x0 + x1) / 2.0)
        if not xs:
            center = 200.0 + index * 80.0
            built.append(
                TableColumnIR(
                    col_idx=index + 1,
                    x_center=center,
                    x_min=center - 30.0,
                    x_max=center + 30.0,
                    kind="VALUE",
                    cell_count=0,
                )
            )
            continue
        center = sum(xs) / len(xs)
        built.append(
            TableColumnIR(
                col_idx=index + 1,
                x_center=center,
                x_min=min(xs) - 8.0,
                x_max=max(xs) + 8.0,
                kind="VALUE",
                cell_count=len(xs),
            )
        )
    return tuple(built)


def _column_index(statement: CanonicalStatement, column_id: str) -> int | None:
    for index, column in enumerate(statement.columns):
        if column.column_id == column_id:
            return index
    return None


def _header_lines(
    document: CanonicalDocument, region: StatementRegion | None
) -> list[CanonicalLine]:
    if region is None:
        return []
    pages = {page.page_number: page for page in document.pages}
    headers: list[CanonicalLine] = []
    for page_number in range(region.page_start, region.page_end + 1):
        page = pages.get(page_number)
        if page is None:
            continue
        for line in page.lines:
            if _is_context_header_line(line):
                headers.append(line)
    return headers


def _is_context_header_line(line: CanonicalLine) -> bool:
    """Keep duration/date/unit header lines even when split_label_and_values sees years."""

    text = line.text.strip()
    if not text:
        return False
    kind = _phrase_kind(text)
    if kind in {"ENTITY", "DURATION", "DATE", "YEAR", "DAYMONTH", "UNIT", "ANNOTATION"}:
        return True
    _label, values = split_label_and_values(text)
    if not values:
        return True
    # Pure calendar fragments (day/year) are header, not monetary body cells.
    if all(re.fullmatch(r"\d{1,2}|19\d{2}|20\d{2}|0{3}", value.replace(",", "")) for value in values):
        return True
    return False


def _line_phrases(line: CanonicalLine) -> list[tuple[str, BBox]]:
    tokens = line.tokens
    if not tokens:
        return []
    if len(tokens) == 1:
        token = tokens[0]
        x0, y0, x1, y1 = token.bbox
        return [(token.text, BBox(x0, y0, x1, y1))]

    heights = [t.bbox[3] - t.bbox[1] for t in tokens]
    typical = sorted(heights)[len(heights) // 2] or 8.0
    gap_limit = max(typical * 1.2, 9.0)
    groups: list[list[CanonicalToken]] = [[tokens[0]]]
    for prev, token in zip(tokens, tokens[1:], strict=False):
        gap = token.bbox[0] - prev.bbox[2]
        if gap > gap_limit:
            groups.append([token])
        else:
            groups[-1].append(token)
    out: list[tuple[str, BBox]] = []
    for group in groups:
        text = " ".join(t.text for t in group).strip()
        if not text:
            continue
        out.append(
            (
                text,
                BBox(
                    min(t.bbox[0] for t in group),
                    min(t.bbox[1] for t in group),
                    max(t.bbox[2] for t in group),
                    max(t.bbox[3] for t in group),
                ),
            )
        )
    return out


def header_h1_metrics(statements: tuple[CanonicalStatement, ...]) -> dict[str, int]:
    from cse_financial_etl.v2.resolution.column_context import context_resolution_metrics

    totals: Counter[str] = Counter()
    for statement in statements:
        totals.update(context_resolution_metrics(statement))
    return dict(totals)


__all__ = ["bind_column_context_h1", "header_h1_metrics"]
