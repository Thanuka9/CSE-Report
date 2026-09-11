"""Compile CanonicalFinancialStatement objects from reconstructed tables (sections 13-14).

One statement is compiled per stable table (header region). Every body cell is
bound to a compiled column; unit typing (currency and scale) is resolved per cell
and per metric *dimension* with explicit evidence ownership before any value is
normalized (audit finding 4).
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from typing import Any

from cse_financial_etl.accounting.row_context import build_row_context, structural_boost
from cse_financial_etl.accounting.semantic_candidates import (
    ConceptHypothesis,
    generate_concept_hypotheses,
    normalize_label,
)
from cse_financial_etl.compiler.canonical_statement import (
    CanonicalFinancialStatement,
    StatementCell,
    StatementRow,
)
from cse_financial_etl.compiler.column_compiler import (
    ColumnSchema,
    StatementColumn,
    compile_column_schema,
)
from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.compiler.structure_normalizer import (
    normalize_entity_term,
    normalize_search_text,
    parse_numeric,
)
from cse_financial_etl.compiler.units import (
    MONETARY,
    PERCENT,
    SCOPE_PAGE,
    SCOPE_ROW,
    UnitDeclaration,
    concept_dimension,
    label_dimension_hint,
    resolve_unit,
)
from cse_financial_etl.document.continuation import ContinuationLink, detect_continuations
from cse_financial_etl.document.document_ir import CanonicalDocumentIR, PageIR, TableIR
from cse_financial_etl.document.region_detector import StatementRegion
from cse_financial_etl.document.table_reconstructor import reconstruct_tables

_SKIP_REGIONS = {"COVER", "OTHER", "RELATED_PARTY"}
_NO_CONCEPT_STATEMENTS = {"CASH_FLOW", "CHANGES_IN_EQUITY"}
_PER_SHARE_ONLY_STATEMENTS = {
    "NOTES",
    "SHARE_INFORMATION",
    "FINANCIAL_HIGHLIGHTS",
    "SEGMENT_INFORMATION",
}
_PER_SHARE_CONCEPTS = {
    "EPS_BASIC",
    "EPS_DILUTED",
    "NAVPS",
    "DPS",
    "WEIGHTED_AVG_SHARES",
    "ORDINARY_SHARES",
}
_TITLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("PROFIT_LOSS", re.compile(r"statement of (?:profit|income)|income statement|profit or loss", re.I)),
    ("COMPREHENSIVE_INCOME", re.compile(r"comprehensive income", re.I)),
    ("FINANCIAL_POSITION", re.compile(r"financial position|balance sheet", re.I)),
    ("CASH_FLOW", re.compile(r"cash flows?", re.I)),
    ("CHANGES_IN_EQUITY", re.compile(r"changes in equity", re.I)),
)
_EPS_CONTINUATION_RE = re.compile(r"^(?:basic|diluted)$")


def compile_statements(
    document: CanonicalDocumentIR,
    regions: list[StatementRegion],
    known: KnownContext,
) -> list[CanonicalFinancialStatement]:
    if not any(page.tables for page in document.pages):
        document = reconstruct_tables(document)
    statements: list[CanonicalFinancialStatement] = []
    pages = {p.page_number: p for p in document.pages}
    continuation_links = {
        (link.to_page, link.statement_type): link
        for link in detect_continuations(document, regions)
        if link.evidenced
    }

    for region in regions:
        if region.statement_type in _SKIP_REGIONS:
            continue
        previous_schemas: dict[tuple[str, int], ColumnSchema] = {}
        for page_no in range(region.page_start, region.page_end + 1):
            page = pages.get(page_no)
            if page is None or not page.tables:
                continue
            page_units = _page_unit_declarations(page)
            for table_index, table in enumerate(page.tables):
                statement_type = _table_statement_type(table, region.statement_type)
                schema = compile_column_schema(table, statement_type=statement_type, known=known)
                link = continuation_links.get((page_no, region.statement_type))
                prior_schema = previous_schemas.get((statement_type, table_index))
                if link is not None and prior_schema is not None:
                    schema = _bridge_evidenced_continuation_context(
                        schema,
                        prior_schema,
                        page,
                        link,
                    )
                rows = _rows_from_table(
                    table,
                    page_no,
                    statement_type,
                    schema,
                    page_units=page_units,
                )
                previous_schemas[(statement_type, table_index)] = schema
                if not rows:
                    continue
                unit_evidence = [d.as_dict() for d in schema.table_units] + [
                    d.as_dict() for d in page_units
                ]
                for col in schema.columns:
                    unit_evidence.extend(d.as_dict() for d in col.unit_declarations)
                statements.append(
                    CanonicalFinancialStatement(
                        issuer_id=known.issuer_id,
                        source_sha256=document.source_sha256,
                        statement_type=statement_type,
                        columns=schema.columns,
                        rows=rows,
                        unit_evidence=unit_evidence,
                        compilation_evidence={
                            "region_confidence": region.confidence,
                            "region_evidence": region.evidence,
                            "region_statement_type": region.statement_type,
                            "table_index": table_index,
                            "table_entity": schema.table_entity,
                            "table_duration_months": schema.table_duration_months,
                            "table_period_end": (
                                schema.table_period_end.isoformat()
                                if schema.table_period_end
                                else None
                            ),
                            "header": schema.evidence,
                            "columns": [
                                {
                                    "column_id": c.column_id,
                                    "kind": c.kind,
                                    "entity": c.entity,
                                    "period_end": c.period_end.isoformat() if c.period_end else None,
                                    "duration_months": c.duration_months,
                                    "role": c.comparison_role,
                                    "currency": c.currency,
                                    "scale": str(c.scale_factor) if c.scale_factor is not None else None,
                                    "path": list(c.context_evidence_ids),
                                    "evidence": c.evidence,
                                    "conflicts": list(c.conflicts),
                                }
                                for c in schema.columns
                            ],
                        },
                        page_start=page_no,
                        page_end=page_no,
                        table_index=table_index,
                        header_conflicts=list(schema.conflicts),
                    )
                )
    return statements


def _bridge_evidenced_continuation_context(
    schema: ColumnSchema,
    previous: ColumnSchema,
    page: PageIR,
    link: ContinuationLink,
) -> ColumnSchema:
    """Bridge only source-owned entity context across an evidenced page boundary.

    The continuation detector has already established adjacency, statement identity,
    numeric structure and repeated source-header evidence. Entity inheritance is
    narrower still: the continuation page must explicitly print exactly one entity
    cue, the preceding source schema must have exactly one matching entity, and the
    VALUE columns must have compatible source dates/durations. Query/KnownContext
    values are never consulted. Any ambiguity or conflict leaves the schema unchanged.
    """

    current_entity = _single_page_entity(page)
    if current_entity is None:
        return schema

    previous_entities = {
        col.entity for col in previous.columns if col.kind == "VALUE" and col.entity is not None
    }
    if previous.table_entity is not None:
        previous_entities.add(previous.table_entity)
    if previous_entities != {current_entity}:
        return schema

    current_explicit = {
        col.entity for col in schema.columns if col.kind == "VALUE" and col.entity is not None
    }
    if current_explicit and current_explicit != {current_entity}:
        return schema
    if not _continuation_columns_compatible(previous, schema):
        return schema

    changed = False
    columns: list[StatementColumn] = []
    for col in schema.columns:
        if col.kind != "VALUE" or col.entity is not None:
            columns.append(col)
            continue
        evidence = dict(col.evidence)
        evidence["entity"] = {
            "text": current_entity,
            "source": "evidenced_cross_page_continuation",
            "source_owned": True,
            "from_page": link.from_page,
            "to_page": link.to_page,
            "continuation_reason": link.reason,
            "compatibility": "matching_source_header_dates",
        }
        columns.append(replace(col, entity=current_entity, evidence=evidence))
        changed = True

    if not changed:
        return schema

    header_evidence = dict(schema.evidence)
    header_evidence["continuation_context"] = {
        "source": "evidenced_cross_page_continuation",
        "source_owned": True,
        "from_page": link.from_page,
        "to_page": link.to_page,
        "statement_type": link.statement_type,
        "entity": current_entity,
        "reason": link.reason,
    }
    return ColumnSchema(
        columns=columns,
        table_entity=current_entity,
        table_duration_months=schema.table_duration_months,
        table_period_end=schema.table_period_end,
        table_units=schema.table_units,
        conflicts=schema.conflicts,
        evidence=header_evidence,
    )


def _single_page_entity(page: PageIR) -> str | None:
    entities = {
        entity
        for line in page.lines[:10]
        if (entity := normalize_entity_term(line.text)) is not None
    }
    if len(entities) != 1:
        return None
    return next(iter(entities))


def _continuation_columns_compatible(previous: ColumnSchema, current: ColumnSchema) -> bool:
    """Require source-header alignment before any continuation inheritance."""

    previous_values = {col.col_idx: col for col in previous.columns if col.kind == "VALUE"}
    current_values = {col.col_idx: col for col in current.columns if col.kind == "VALUE"}
    common = sorted(previous_values.keys() & current_values.keys())
    if not common:
        return False

    matching_dates = 0
    for col_idx in common:
        before = previous_values[col_idx]
        after = current_values[col_idx]
        if before.period_end is not None and after.period_end is not None:
            if before.period_end != after.period_end:
                return False
            matching_dates += 1
        if (
            before.duration_months is not None
            and after.duration_months is not None
            and before.duration_months != after.duration_months
        ):
            return False
    return matching_dates > 0


def _table_statement_type(table: TableIR, region_type: str) -> str:
    blob = " ".join(table.title_texts)
    for statement_type, pattern in _TITLE_RULES:
        if pattern.search(blob):
            return statement_type
    return region_type


def _page_unit_declarations(page: PageIR) -> list[UnitDeclaration]:
    decls: list[UnitDeclaration] = []
    seen: set[str] = set()
    for t_idx, table in enumerate(page.tables):
        texts = list(table.footer_texts)
        if t_idx == 0:
            texts.extend(table.title_texts)
        for i, text in enumerate(texts):
            if text in seen:
                continue
            seen.add(text)
            decl = UnitDeclaration.from_text(
                text,
                scope=SCOPE_PAGE,
                owner=f"page:{page.page_number}:t{t_idx}:l{i}",
                page=page.page_number,
            )
            if decl is not None and (decl.currency or decl.scale_explicit) and not decl.per_share:
                decls.append(decl)
    return decls


def _rows_from_table(
    table: TableIR,
    page_no: int,
    statement_type: str,
    schema: ColumnSchema,
    *,
    page_units: list[UnitDeclaration],
) -> list[StatementRow]:
    by_row: dict[int, list[Any]] = {}
    for cell in table.cells:
        by_row.setdefault(cell.row_idx, []).append(cell)
    row_indices = sorted(by_row)
    columns_by_idx: dict[int, StatementColumn] = {c.col_idx: c for c in schema.columns}
    meta: list[tuple[str, str, int]] = []
    labels: dict[int, str] = {}
    for row_idx in row_indices:
        label_cell = next((c for c in by_row[row_idx] if c.col_idx == 0), None)
        label = label_cell.raw_text if label_cell else ""
        labels[row_idx] = label
        meta.append(
            (f"p{page_no}-t{table_index_of(table)}-r{row_idx}", normalize_search_text(label), 0)
        )

    unit_lines = sorted(table.unit_lines, key=lambda u: u.row_idx)
    rows: list[StatementRow] = []
    for position, row_idx in enumerate(row_indices):
        cells = by_row[row_idx]
        label = labels[row_idx]
        match_label = _label_for_matching(label, row_indices, position, labels)
        ctx = build_row_context(meta, position) if meta else None
        hyps = _hypotheses(match_label, statement_type, ctx)
        row_id = meta[position][0]

        row_decls = _row_declarations(label, row_id=row_id, page=page_no)
        active_unit_line = None
        for unit_line in unit_lines:
            if unit_line.row_idx < row_idx:
                active_unit_line = unit_line
        hint = label_dimension_hint(label)
        dimensions = {concept_dimension(h.concept) for h in hyps}
        dimensions.add(hint or MONETARY)
        primary = concept_dimension(hyps[0].concept) if hyps else (hint or MONETARY)

        cell_map: dict[str, StatementCell] = {}
        for cell in cells:
            if cell.col_idx == 0:
                continue
            col = columns_by_idx.get(cell.col_idx)
            if col is None:
                continue
            value = parse_numeric(cell.raw_text)
            col_id = col.column_id
            line_decls = list(row_decls)
            if active_unit_line is not None:
                for phrase in active_unit_line.phrases:
                    if _phrase_in_column(phrase.bbox.center_x, col, table):
                        decl = UnitDeclaration.from_text(
                            phrase.text,
                            scope=SCOPE_ROW,
                            owner=f"unitline:{page_no}:r{active_unit_line.row_idx}:{col_id}",
                            page=page_no,
                        )
                        if decl is not None:
                            line_decls.append(decl)
            dimension_values: dict[str, Decimal | None] = {}
            unit_resolutions: dict[str, dict[str, Any]] = {}
            if col.kind == "VALUE" and value is not None:
                for dimension in sorted(dimensions):
                    resolution = resolve_unit(
                        dimension,
                        row=line_decls,
                        column=list(col.unit_declarations),
                        table=list(schema.table_units),
                        page=list(page_units),
                    )
                    unit_resolutions[dimension] = resolution.as_dict()
                    if resolution.resolved and resolution.scale is not None:
                        dimension_values[dimension] = value * resolution.scale
                    else:
                        dimension_values[dimension] = None
            elif col.kind == "PERCENT" and value is not None:
                dimension_values[PERCENT] = value
                unit_resolutions[PERCENT] = {
                    "dimension": PERCENT,
                    "status": "RESOLVED",
                    "scale": "1",
                }
            normalized = dimension_values.get(primary) if col.kind == "VALUE" else None
            cell_map[col_id] = StatementCell(
                raw_text=cell.raw_text,
                raw_numeric=value,
                normalized_value=normalized,
                source_page=page_no,
                source_bbox=cell.bbox,
                column_id=col_id,
                effective_unit_evidence_ids=tuple(
                    unit_resolutions.get(primary, {}).get("evidence_ids", [])
                    if col.kind == "VALUE"
                    else ()
                ),
                dimension_values=dimension_values,
                unit_resolutions=unit_resolutions,
                primary_dimension=(
                    primary
                    if col.kind == "VALUE"
                    else (PERCENT if col.kind == "PERCENT" else None)
                ),
            )
        rows.append(
            StatementRow(
                row_id=row_id,
                raw_label=label,
                normalized_label=normalize_search_text(label),
                indentation_level=0,
                parent_section=ctx.parent_section if ctx else None,
                cells=cell_map,
                hypotheses=hyps,
                source_line_ids=tuple(table.row_line_ids.get(row_idx, ())),
                row_unit_evidence=[d.as_dict() for d in row_decls],
                dimension_hint=hint,
            )
        )
    return rows


def table_index_of(table: TableIR) -> int:
    return round(table.bbox.y0)


def _label_for_matching(
    label: str,
    row_indices: list[int],
    position: int,
    labels: dict[int, str],
) -> str:
    normalized = normalize_label(label)
    if _EPS_CONTINUATION_RE.match(normalized):
        for back in range(1, 4):
            if position - back < 0:
                break
            previous = labels[row_indices[position - back]]
            if re.search(r"per\s+(?:ordinary\s+)?share", previous, re.I):
                base = re.sub(r"\b(?:basic|diluted)\b", "", previous, flags=re.I)
                return f"{base} {normalized}"
    return label


def _hypotheses(label: str, statement_type: str, ctx: Any) -> list[ConceptHypothesis]:
    if statement_type in _NO_CONCEPT_STATEMENTS:
        return []
    hyps: list[ConceptHypothesis] = []
    for hyp in generate_concept_hypotheses(label, statement_type=statement_type):
        boost = structural_boost(ctx, hyp.concept) if ctx else 0.0
        if boost:
            boosted = generate_concept_hypotheses(
                label,
                statement_type=statement_type,
                structural_score=boost,
            )
            match = next((h for h in boosted if h.concept == hyp.concept), None)
            if match is not None:
                hyp = match
        hyps.append(hyp)
    if statement_type in _PER_SHARE_ONLY_STATEMENTS:
        hyps = [h for h in hyps if h.concept in _PER_SHARE_CONCEPTS]
    hyps.sort(key=lambda h: (h.total_score, h.concept), reverse=True)
    return hyps


def _row_declarations(label: str, *, row_id: str, page: int) -> list[UnitDeclaration]:
    from cse_financial_etl.compiler.units import row_unit_declarations

    return row_unit_declarations(label, owner=f"row:{row_id}", page=page)


def _phrase_in_column(x: float, col: StatementColumn, table: TableIR) -> bool:
    geom = next((c for c in table.columns if c.col_idx == col.col_idx), None)
    if geom is None:
        return False
    return geom.x_min <= x <= geom.x_max
