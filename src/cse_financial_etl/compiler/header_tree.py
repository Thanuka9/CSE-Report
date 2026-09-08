"""Header tree compilation — bind every numeric column to its spatial header path (§11).

Audit finding 3 rules:

* Dates are parsed from what is printed (day, month, year); a bare year is only
  completed with a day/month that is printed in a header phrase bound to the
  same column (caption / parent phrase).  Nothing is defaulted to 31 December.
* Entity, duration and comparison role stay ``None`` when the table does not say.
* Parent phrases (``Group`` / ``Company`` / ``Six months ended``) are assigned to
  column blocks by geometry (periodic signature of the leaf row, else nearest
  parent by horizontal distance) — never by splitting at the midpoint.
* Comparison roles are derived from the dates inside each (entity, duration)
  block: the latest period is CURRENT, others COMPARATIVE.
* Expected metadata (``KnownContext``) is only used to *detect conflicts*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.compiler.structure_normalizer import (
    compose_date,
    is_instant_phrase,
    normalize_date,
    normalize_duration_phrase,
    normalize_entity_term,
    parse_day_month,
    parse_year,
)
from cse_financial_etl.compiler.units import SCOPE_COLUMN, SCOPE_TABLE, UnitDeclaration
from cse_financial_etl.document.document_ir import HeaderPhraseIR, TableColumnIR, TableIR

_LEAF_KINDS = {"DATE", "YEAR", "DAYMONTH", "UNIT", "ANNOTATION", "NOTE", "CHANGE"}
_BLOCK_KINDS = {"ENTITY", "DURATION"}
_INSTANT_STATEMENTS = {"FINANCIAL_POSITION"}


@dataclass(frozen=True, slots=True)
class HeaderNode:
    text: str
    entity: str | None = None
    comparison_role: str | None = None
    duration_months: int | None = None
    period_end: date | None = None
    children: tuple[HeaderNode, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledHeaderColumn:
    column_id: str
    entity: str | None
    comparison_role: str | None
    duration_months: int | None
    period_end: date | None
    path: tuple[str, ...]
    col_idx: int = 0
    kind: str = "VALUE"
    period_start: date | None = None
    temporal_type: str | None = None
    currency: str | None = None
    scale_factor: Decimal | None = None
    scale_explicit: bool = False
    annotation: str | None = None
    unit_declarations: tuple[UnitDeclaration, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    conflicts: tuple[str, ...] = ()


@dataclass
class HeaderCompilation:
    columns: list[CompiledHeaderColumn]
    table_entity: str | None
    table_duration_months: int | None
    table_period_end: date | None
    table_units: list[UnitDeclaration]
    conflicts: list[str]
    evidence: dict[str, Any]


def compile_header_tree(
    table: TableIR,
    header_texts: list[str] | None = None,
    *,
    statement_type: str | None = None,
    known: KnownContext | None = None,
) -> list[CompiledHeaderColumn]:
    """Backward-compatible entry point returning only the compiled columns."""

    return compile_header(table, statement_type=statement_type, known=known).columns


def compile_header(
    table: TableIR,
    *,
    statement_type: str | None = None,
    known: KnownContext | None = None,
) -> HeaderCompilation:
    columns = [c for c in table.columns if c.col_idx > 0]
    value_cols = [c for c in columns if c.kind == "VALUE"]
    cell_centres = _cell_centres(table)
    phrases_by_row: dict[int, list[HeaderPhraseIR]] = {}
    for phrase in table.header_phrases:
        phrases_by_row.setdefault(phrase.row_idx, []).append(phrase)

    bound: dict[int, dict[str, list[HeaderPhraseIR]]] = {c.col_idx: {} for c in columns}
    conflicts: list[str] = []

    for row_idx in sorted(phrases_by_row):
        row_phrases = sorted(phrases_by_row[row_idx], key=lambda p: p.bbox.x0)
        for kind in {p.kind for p in row_phrases}:
            same_kind = [p for p in row_phrases if p.kind == kind]
            if kind in _LEAF_KINDS or kind == "TEXT":
                for phrase in same_kind:
                    col = _leaf_column(phrase, columns)
                    if col is not None:
                        bound[col.col_idx].setdefault(kind, []).append(phrase)
                continue
            if kind in _BLOCK_KINDS:
                assignment = _assign_blocks(same_kind, value_cols, columns, table, cell_centres)
                for col_idx, phrase in assignment.items():
                    bound[col_idx].setdefault(kind, []).append(phrase)

    # Table-level evidence: caption phrases + title lines.
    caption_texts = [p.text for p in table.caption_phrases]
    title_texts = list(table.title_texts)
    table_entity = _single_entity(title_texts + caption_texts)
    caption_duration = _first_duration(caption_texts + title_texts)
    caption_instant = any(is_instant_phrase(t) for t in caption_texts + title_texts)
    caption_date = _first_date(caption_texts + title_texts)
    caption_day_month = _first_day_month(caption_texts + title_texts)
    table_units: list[UnitDeclaration] = []
    for i, text in enumerate(title_texts):
        decl = UnitDeclaration.from_text(text, scope=SCOPE_TABLE, owner=f"title:{table.page_number}:{i}", page=table.page_number)
        if decl is not None and (decl.currency or decl.scale_explicit):
            table_units.append(decl)
    for phrase in table.caption_phrases:
        if phrase.kind == "UNIT":
            decl = UnitDeclaration.from_text(
                phrase.text, scope=SCOPE_TABLE, owner=f"caption:{table.page_number}:r{phrase.row_idx}", page=table.page_number
            )
            if decl is not None:
                table_units.append(decl)

    instant_statement = statement_type in _INSTANT_STATEMENTS
    # When any column header states an explicit month count ("Quarter", "Six months"), a sibling
    # column that only says "Period ended" is a *different* (unstated) duration — the caption
    # duration must not be copied onto it (NDB: "Period ended" = YTD next to "Quarter ended").
    explicit_column_durations = any(
        normalize_duration_phrase(p.text) is not None for p in table.header_phrases if p.kind == "DURATION"
    )

    compiled: list[CompiledHeaderColumn] = []
    for col in columns:
        kinds = bound[col.col_idx]
        evidence: dict[str, Any] = {}
        col_conflicts: list[str] = []

        # Entity.
        entity: str | None = None
        entity_phrases = kinds.get("ENTITY", [])
        if entity_phrases:
            terms = {normalize_entity_term(p.text) for p in entity_phrases} - {None}
            if len(terms) == 1:
                entity = terms.pop()
                evidence["entity"] = _phrase_evidence(entity_phrases[0], "header_block")
            elif len(terms) > 1:
                col_conflicts.append("ENTITY_CONFLICT:" + "|".join(sorted(terms)))  # type: ignore[arg-type]
        if entity is None:
            # "Company for the three months ended 30 June 2026" carries the entity inside the block phrase.
            embedded = _single_entity([p.text for p in kinds.get("DURATION", [])])
            if embedded is not None:
                entity = embedded
                evidence["entity"] = _phrase_evidence(kinds["DURATION"][0], "header_block_embedded_entity")
        if entity is None and table_entity is not None and not col_conflicts:
            entity = table_entity
            evidence["entity"] = {"text": table_entity, "source": "table_title"}

        # Duration phrases bound to this column (block) — may also carry a date.
        duration_phrases = kinds.get("DURATION", [])
        duration: int | None = None
        instant = instant_statement or caption_instant
        duration_source: dict[str, Any] | None = None
        for phrase in duration_phrases:
            months = normalize_duration_phrase(phrase.text)
            if is_instant_phrase(phrase.text):
                instant = True
            if months is not None:
                if duration is not None and months != duration:
                    col_conflicts.append(f"DURATION_CONFLICT:{duration}|{months}")
                duration = months
                duration_source = _phrase_evidence(phrase, "header_block")
        period_ended_only = duration is None and any(
            re.search(r"\bperiod\b", p.text.lower()) and not is_instant_phrase(p.text) for p in duration_phrases
        )
        if duration is None and caption_duration is not None and not (period_ended_only and explicit_column_durations):
            duration = caption_duration
            duration_source = {"text": caption_duration, "source": "table_caption"}
            period_ended_only = False

        # Period end.
        period_end: date | None = None
        period_source: dict[str, Any] | None = None
        date_phrases = kinds.get("DATE", [])
        year_phrases = kinds.get("YEAR", [])
        for phrase in date_phrases:
            parsed = normalize_date(phrase.text)
            if parsed is not None:
                if period_end is not None and parsed != period_end:
                    col_conflicts.append(f"PERIOD_CONFLICT:{period_end}|{parsed}")
                period_end = parsed
                period_source = _phrase_evidence(phrase, "header_leaf")
        if period_end is None:
            for phrase in duration_phrases:
                embedded = normalize_date(phrase.text)
                if embedded is not None and _phrase_right_aligned(phrase, col):
                    period_end = embedded
                    period_source = _phrase_evidence(phrase, "header_block_embedded_date")
                    break
        if period_end is None and year_phrases:
            year = parse_year(year_phrases[0].text)
            day_month = None
            dm_source = None
            for phrase in kinds.get("DAYMONTH", []):
                day_month = parse_day_month(phrase.text)
                if day_month is not None:
                    dm_source = _phrase_evidence(phrase, "header_leaf_day_month")
                    break
            for phrase in duration_phrases if day_month is None else []:
                day_month = parse_day_month(phrase.text)
                if day_month is None:
                    full = normalize_date(phrase.text)
                    if full is not None:
                        day_month = (full.day, full.month)
                if day_month is not None:
                    dm_source = _phrase_evidence(phrase, "header_block_day_month")
                    break
            if day_month is None and caption_day_month is not None:
                day_month = caption_day_month
                dm_source = {"source": "table_caption"}
            if day_month is None and caption_date is not None:
                day_month = (caption_date.day, caption_date.month)
                dm_source = {"source": "table_caption_date"}
            if year is not None and day_month is not None:
                period_end = compose_date(year, day_month[1], day_month[0])
                period_source = {
                    "year": _phrase_evidence(year_phrases[0], "header_leaf"),
                    "day_month": dm_source,
                }
            elif year is not None:
                evidence["period_year_only"] = year
        if period_end is None and not date_phrases and not year_phrases and caption_date is not None and len(value_cols) <= 1:
            period_end = caption_date
            period_source = {"source": "table_caption_date"}

        # Units declared on the column header.
        unit_decls: list[UnitDeclaration] = []
        for phrase in kinds.get("UNIT", []):
            decl = UnitDeclaration.from_text(
                phrase.text,
                scope=SCOPE_COLUMN,
                owner=f"col:{table.page_number}:c{col.col_idx}:r{phrase.row_idx}",
                page=table.page_number,
            )
            if decl is not None:
                unit_decls.append(decl)
        currency = next((d.currency for d in unit_decls if d.currency), None)
        explicit_scales = {d.scale for d in unit_decls if d.scale_explicit}
        scale = None
        scale_explicit = False
        if len(explicit_scales) == 1:
            scale = explicit_scales.pop()
            scale_explicit = True
        elif len(explicit_scales) > 1:
            col_conflicts.append("UNIT_SCALE_CONFLICT")
        elif currency is not None:
            scale = Decimal("1")

        annotation = None
        if kinds.get("ANNOTATION"):
            annotation = kinds["ANNOTATION"][0].text.strip("() ").upper()

        temporal_type = None
        if col.kind == "VALUE":
            if instant and duration is None:
                temporal_type = "instant"
            elif duration is not None or period_ended_only:
                temporal_type = "duration"
        if instant_statement:
            duration = None
            temporal_type = "instant"

        path = tuple(
            p.text
            for row in sorted(phrases_by_row)
            for p in phrases_by_row[row]
            if any(p is q for group in kinds.values() for q in group)
        )
        if duration_source:
            evidence["duration"] = duration_source
        if period_source:
            evidence["period_end"] = period_source
        if period_ended_only:
            evidence["period_ended_only"] = True
        if unit_decls:
            evidence["units"] = [d.as_dict() for d in unit_decls]
        compiled.append(
            CompiledHeaderColumn(
                column_id=f"c{col.col_idx}",
                col_idx=col.col_idx,
                kind=col.kind,
                entity=entity,
                comparison_role=None,
                duration_months=duration,
                period_end=period_end,
                period_start=None,
                temporal_type=temporal_type,
                path=path,
                currency=currency,
                scale_factor=scale,
                scale_explicit=scale_explicit,
                annotation=annotation,
                unit_declarations=tuple(unit_decls),
                evidence=evidence,
                conflicts=tuple(col_conflicts),
            )
        )

    compiled = _derive_period_ended_durations(compiled)
    compiled = _assign_roles(compiled)
    compiled = _period_starts(compiled)

    if known is not None:
        for col in compiled:
            if col.kind != "VALUE" or col.comparison_role != "CURRENT":
                continue
            if (
                col.period_end is not None
                and known.target_period_end
                and col.period_end != known.target_period_end
                and (col.duration_months == known.target_duration_months or col.duration_months is None)
            ):
                conflicts.append(
                    f"PERIOD_END_MISMATCH:{col.column_id}:{col.period_end.isoformat()}!={known.target_period_end.isoformat()}"
                )
    for col in compiled:
        conflicts.extend(f"{col.column_id}:{c}" for c in col.conflicts)

    return HeaderCompilation(
        columns=compiled,
        table_entity=table_entity,
        table_duration_months=caption_duration,
        table_period_end=caption_date,
        table_units=table_units,
        conflicts=conflicts,
        evidence={
            "title_texts": title_texts,
            "caption_texts": caption_texts,
            "header_rows": list(table.header_rows),
        },
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _cell_centres(table: TableIR) -> dict[int, float]:
    sums: dict[int, list[float]] = {}
    for cell in table.cells:
        if cell.col_idx == 0:
            continue
        sums.setdefault(cell.col_idx, []).append(cell.bbox.center_x)
    return {k: sum(v) / len(v) for k, v in sums.items() if v}


def _leaf_column(phrase: HeaderPhraseIR, columns: list[TableColumnIR]) -> TableColumnIR | None:
    centre = phrase.bbox.center_x
    for col in columns:
        if col.x_min <= centre <= col.x_max:
            return col
    for col in columns:
        if col.x_min <= phrase.bbox.x1 <= col.x_max + 2:
            return col
    return None


def _phrase_right_aligned(phrase: HeaderPhraseIR, col: TableColumnIR) -> bool:
    return col.x_min <= phrase.bbox.x1 <= col.x_max + 2 or abs(phrase.bbox.x1 - col.x_center) <= 6


def _assign_blocks(
    parents: list[HeaderPhraseIR],
    value_cols: list[TableColumnIR],
    all_cols: list[TableColumnIR],
    table: TableIR,
    cell_centres: dict[int, float],
) -> dict[int, HeaderPhraseIR]:
    """Map value columns to parent phrases (periodic signature, else nearest parent)."""

    if not parents or not value_cols:
        return {}
    parents = sorted(parents, key=lambda p: p.bbox.center_x)
    ordered = sorted(value_cols, key=lambda c: c.x_center)
    # Columns without any period leaf cannot be period blocks when their siblings have one
    # (undetected note / reference columns); leave them unbound.
    with_leaf = [c for c in ordered if _leaf_signature(c, table) is not None]
    if len(with_leaf) >= 2 and len(with_leaf) < len(ordered):
        ordered = with_leaf
    assignment: dict[int, HeaderPhraseIR] = {}
    if len(parents) == 1:
        for col in ordered:
            assignment[col.col_idx] = parents[0]
    elif len(parents) >= len(ordered):
        for col in ordered:
            centre = cell_centres.get(col.col_idx, (col.x_min + col.x_max) / 2)
            assignment[col.col_idx] = min(parents, key=lambda p: abs(p.bbox.center_x - centre))
    else:
        blocks = _periodic_blocks(ordered, table, len(parents))
        if blocks is not None:
            for parent, block in zip(parents, blocks, strict=False):
                for col in block:
                    assignment[col.col_idx] = parent
        else:
            for col in ordered:
                centre = cell_centres.get(col.col_idx, (col.x_min + col.x_max) / 2)
                assignment[col.col_idx] = min(parents, key=lambda p: abs(p.bbox.center_x - centre))
    # Percent / note columns follow the value column immediately to their left.
    ordered_all = sorted(all_cols, key=lambda c: c.x_center)
    last_parent: HeaderPhraseIR | None = None
    for col in ordered_all:
        if col.col_idx in assignment:
            last_parent = assignment[col.col_idx]
        elif col.kind == "PERCENT" and last_parent is not None:
            assignment[col.col_idx] = last_parent
    return assignment


def _periodic_blocks(
    ordered: list[TableColumnIR], table: TableIR, n_parents: int
) -> list[list[TableColumnIR]] | None:
    if n_parents <= 0 or len(ordered) % n_parents != 0:
        return None
    period = len(ordered) // n_parents
    signature = [_leaf_signature(col, table) for col in ordered]
    if any(s is None for s in signature):
        return None
    for i in range(len(ordered) - period):
        if signature[i] != signature[i + period]:
            return None
    return [ordered[i * period : (i + 1) * period] for i in range(n_parents)]


def _leaf_signature(col: TableColumnIR, table: TableIR) -> str | None:
    value_columns = [c for c in table.columns if c.col_idx > 0]
    leaves = []
    for p in table.header_phrases:
        if p.kind not in {"DATE", "YEAR", "DAYMONTH"}:
            continue
        owner = _leaf_column(p, value_columns)
        if owner is not None and owner.col_idx == col.col_idx:
            leaves.append(p.text.strip())
    if not leaves:
        # A duration phrase ending in a full date that is right-aligned to this column
        # ("For the quarter ended 30 June 2026" over the first column) is its leaf.
        for p in table.header_phrases:
            if p.kind == "DURATION" and _phrase_right_aligned(p, col):
                embedded = normalize_date(p.text)
                if embedded is not None:
                    leaves.append(str(embedded.year))
                    break
    return "|".join(leaves) if leaves else None


def _phrase_evidence(phrase: HeaderPhraseIR, source: str) -> dict[str, Any]:
    return {
        "text": phrase.text,
        "row": phrase.row_idx,
        "bbox": [round(phrase.bbox.x0, 1), round(phrase.bbox.y0, 1), round(phrase.bbox.x1, 1), round(phrase.bbox.y1, 1)],
        "source": source,
    }


def _single_entity(texts: list[str]) -> str | None:
    found: set[str] = set()
    for text in texts:
        lower = text.lower()
        for match in re.finditer(r"\b(group|company|bank|consolidated|separate)\b", lower):
            term = normalize_entity_term(match.group(1))
            if term:
                found.add(term)
    return found.pop() if len(found) == 1 else None


def _first_duration(texts: list[str]) -> int | None:
    for text in texts:
        months = normalize_duration_phrase(text)
        if months is not None:
            return months
    return None


def _first_date(texts: list[str]) -> date | None:
    for text in texts:
        parsed = normalize_date(text)
        if parsed is not None:
            return parsed
    return None


def _first_day_month(texts: list[str]) -> tuple[int, int] | None:
    for text in texts:
        parsed = parse_day_month(text)
        if parsed is not None:
            return parsed
    return None


def _derive_period_ended_durations(columns: list[CompiledHeaderColumn]) -> list[CompiledHeaderColumn]:
    """``Period ended 30.06.2026`` next to ``Year ended 31.03.2026`` → 3 months (printed maths)."""

    year_ends = [c.period_end for c in columns if c.duration_months == 12 and c.period_end is not None]
    if not year_ends:
        return columns
    fy_month = year_ends[0].month
    out: list[CompiledHeaderColumn] = []
    for col in columns:
        if col.duration_months is None and col.evidence.get("period_ended_only") and col.period_end is not None:
            months = (col.period_end.month - fy_month) % 12
            months = 12 if months == 0 else months
            if months in {3, 6, 9, 12}:
                evidence = dict(col.evidence)
                evidence["duration"] = {
                    "source": "derived_from_year_end_column",
                    "fiscal_year_end_month": fy_month,
                    "months": months,
                }
                col = _replace(col, duration_months=months, temporal_type="duration", evidence=evidence)
        out.append(col)
    return out


def _assign_roles(columns: list[CompiledHeaderColumn]) -> list[CompiledHeaderColumn]:
    groups: dict[tuple[Any, ...], list[CompiledHeaderColumn]] = {}
    for col in columns:
        if col.kind != "VALUE":
            continue
        groups.setdefault((col.entity, col.duration_months, col.temporal_type), []).append(col)
    role_by_id: dict[str, str | None] = {}
    for members in groups.values():
        dated = [c for c in members if c.period_end is not None]
        if not dated:
            continue
        latest = max(c.period_end for c in dated)  # type: ignore[type-var]
        for col in members:
            if col.period_end is None:
                role_by_id[col.column_id] = None
            elif col.period_end == latest:
                role_by_id[col.column_id] = "CURRENT"
            else:
                role_by_id[col.column_id] = "COMPARATIVE"
    return [_replace(c, comparison_role=role_by_id.get(c.column_id)) for c in columns]


def _period_starts(columns: list[CompiledHeaderColumn]) -> list[CompiledHeaderColumn]:
    """First day of the month ``duration`` months before the period end month."""

    out: list[CompiledHeaderColumn] = []
    for col in columns:
        if col.period_end is not None and col.duration_months:
            month = col.period_end.month - col.duration_months + 1
            year = col.period_end.year
            while month <= 0:
                month += 12
                year -= 1
            col = _replace(col, period_start=compose_date(year, month, 1))
        out.append(col)
    return out


def _replace(col: CompiledHeaderColumn, **changes: Any) -> CompiledHeaderColumn:
    data = {
        "column_id": col.column_id,
        "entity": col.entity,
        "comparison_role": col.comparison_role,
        "duration_months": col.duration_months,
        "period_end": col.period_end,
        "path": col.path,
        "col_idx": col.col_idx,
        "kind": col.kind,
        "period_start": col.period_start,
        "temporal_type": col.temporal_type,
        "currency": col.currency,
        "scale_factor": col.scale_factor,
        "scale_explicit": col.scale_explicit,
        "annotation": col.annotation,
        "unit_declarations": col.unit_declarations,
        "evidence": col.evidence,
        "conflicts": col.conflicts,
    }
    data.update(changes)
    return CompiledHeaderColumn(**data)
