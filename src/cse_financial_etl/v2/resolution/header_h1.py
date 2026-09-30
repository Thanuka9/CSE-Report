"""H1 header engine: V1 header_tree geometry adapted onto V2 CanonicalStatement.

H0 remains the production default. H1 is challenger-only for bake-off.
Does not copy query-target metadata. Rejects table-title/caption silent fills.
"""

from __future__ import annotations

import itertools
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Literal

from cse_financial_etl.compiler.header_tree import compile_header
from cse_financial_etl.compiler.structure_normalizer import (
    compose_date,
    normalize_date,
    parse_day_month,
)
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
    _column_kinds,
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
    calendar_day_month = _unique_header_day_month(table.header_phrases)
    kinds = _column_kinds(statement)
    columns: list[StatementColumn] = []
    for index, (statement_column, compiled) in enumerate(
        zip(statement.columns, value_cols, strict=True)
    ):
        kind = kinds[index] if index < len(kinds) else "monetary"
        if kind == "note":
            columns.append(StatementColumn(column_id=statement_column.column_id))
            continue
        if kind == "percent":
            columns.append(
                StatementColumn(
                    column_id=statement_column.column_id,
                    unit_dimension=UnitDimension.PERCENTAGE,
                    monetary_scale=Decimal("1"),
                    unit_evidence=evidence,
                )
            )
            continue
        columns.append(
            _map_compiled_column(
                statement_column,
                compiled,
                evidence=evidence,
                default_unit=default_unit,
                statement_type=statement.statement_type,
                calendar_day_month=calendar_day_month,
            )
        )

    columns = _assign_comparison_roles(columns)
    if partial_monetary == "cascade":
        columns = _fail_closed_partial_monetary_columns(statement, columns)
    return statement.model_copy(update={"columns": tuple(columns)})


def _unique_header_day_month(
    phrases: tuple[HeaderPhraseIR, ...],
) -> tuple[int, int] | None:
    """Single shared day/month printed in header DATE/DURATION phrases.

    Used to complete year-only columns when the calendar day/month leaf is
    geometrically bound to only one side of a multi-column header. Evidence
    comes from header phrases, not caption silent fill or query context.
    """

    found: set[tuple[int, int]] = set()
    for phrase in phrases:
        if phrase.kind not in {"DATE", "DAYMONTH", "DURATION"}:
            continue
        full = normalize_date(phrase.text)
        if full is not None:
            found.add((full.day, full.month))
            continue
        day_month = parse_day_month(phrase.text)
        if day_month is not None:
            found.add(day_month)
    if len(found) == 1:
        return next(iter(found))
    return None


def _assign_comparison_roles(columns: list[StatementColumn]) -> list[StatementColumn]:
    """CURRENT/COMPARATIVE from sibling header dates after period completion."""

    groups: dict[tuple[object, object], list[int]] = {}
    for index, column in enumerate(columns):
        if column.unit_dimension is UnitDimension.PERCENTAGE:
            continue
        if column.period_end is None:
            continue
        key = (column.entity_scope, column.duration_months)
        groups.setdefault(key, []).append(index)

    role_by_index: dict[int, ComparisonRole] = {}
    for indices in groups.values():
        dated = [columns[i] for i in indices if columns[i].period_end is not None]
        if len(dated) != len(indices):
            continue
        latest = max(col.period_end for col in dated if col.period_end is not None)
        for index in indices:
            period = columns[index].period_end
            if period is None:
                continue
            role_by_index[index] = (
                ComparisonRole.CURRENT if period == latest else ComparisonRole.COMPARATIVE
            )

    out: list[StatementColumn] = []
    for index, column in enumerate(columns):
        role = role_by_index.get(index)
        if role is None or column.comparison_role is not None:
            out.append(column)
            continue
        out.append(
            column.model_copy(
                update={
                    "comparison_role": role,
                    "comparison_evidence": column.period_evidence,
                }
            )
        )
    return out


def _map_compiled_column(
    statement_column: StatementColumn,
    compiled: object,
    *,
    evidence: tuple[SourceRef, ...],
    default_unit: tuple[str | None, Decimal | None, UnitDimension | None],
    statement_type: StatementType,
    calendar_day_month: tuple[int, int] | None = None,
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
    # Year-only leaves + one shared header day/month (evidence-backed DATE phrase).
    if period_end is None and calendar_day_month is not None:
        year = entity_ev.get("period_year_only")
        if isinstance(year, int):
            period_end = compose_date(year, calendar_day_month[1], calendar_day_month[0])

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
    table_bbox = BBox(min([*xs, 0.0]), ys[0], max([*xs, 400.0]), ys[1])

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
    return bool(all(re.fullmatch(r"\d{1,2}|19\d{2}|20\d{2}|0{3}", value.replace(",", "")) for value in values))


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
    for prev, token in itertools.pairwise(tokens):
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
