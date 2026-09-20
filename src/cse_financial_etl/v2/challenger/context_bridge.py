"""Bind V1 header/statement/unit evidence onto physical cell observations.

Uses V1 ``compile_header`` / title→statement typing only — never issuer KnownContext,
production entity, or workbook values. Incomplete context stays unresolved.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from cse_financial_etl.compiler.header_tree import CompiledHeaderColumn, compile_header
from cse_financial_etl.compiler.units import (
    MONETARY,
    PER_SHARE,
    concept_dimension,
    label_dimension_hint,
    resolve_unit,
    row_unit_declarations,
)
from cse_financial_etl.document.document_ir import TableIR
from cse_financial_etl.v2.challenger.models import V1SourceObservation
from cse_financial_etl.v2.contracts.enums import ComparisonRole, EntityScope, UnitDimension
from cse_financial_etl.v2.contracts.provenance import SourceRef

_TITLE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("INCOME_STATEMENT", re.compile(r"profit|income|comprehensive", re.I)),
    ("BALANCE_SHEET", re.compile(r"financial position|balance sheet", re.I)),
    ("CASH_FLOW", re.compile(r"cash flows?", re.I)),
    ("CHANGES_IN_EQUITY", re.compile(r"changes in equity", re.I)),
)

_ENTITY_MAP = {
    "COMPANY": EntityScope.COMPANY,
    "GROUP": EntityScope.GROUP,
    "BANK": EntityScope.BANK,
    "CONSOLIDATED": EntityScope.CONSOLIDATED,
    "SEPARATE": EntityScope.SEPARATE,
}

_COMPARISON_MAP = {
    "CURRENT": ComparisonRole.CURRENT,
    "COMPARATIVE": ComparisonRole.COMPARATIVE,
}

# V1 compile_header statement_type strings
_V1_STATEMENT_TYPE = {
    "INCOME_STATEMENT": "PROFIT_LOSS",
    "BALANCE_SHEET": "FINANCIAL_POSITION",
    "CASH_FLOW": "CASH_FLOW",
    "CHANGES_IN_EQUITY": "CHANGES_IN_EQUITY",
}


def statement_hint_from_titles(titles: tuple[str, ...]) -> str | None:
    if not titles:
        return None
    blob = " ".join(titles)
    for hint, pattern in _TITLE_RULES:
        if pattern.search(blob):
            return hint
    return None


def bridge_observation_context(
    observation: V1SourceObservation,
    *,
    table: TableIR,
    column: CompiledHeaderColumn | None,
    page_unit_decls: list | None = None,
    table_unit_decls: list | None = None,
) -> V1SourceObservation:
    """Attach source-owned header context to one observation when evidence exists."""

    if column is None:
        return observation

    reasons = [code for code in observation.reason_codes if code != "DISCOVERY_ONLY"]
    notes = list(observation.evidence_notes)
    notes.append("v1_header_bridge")
    if column.path:
        notes.append("header_path:" + " | ".join(column.path))
    if column.evidence:
        notes.append("header_evidence_keys:" + ",".join(sorted(column.evidence)[:12]))

    entity = _ENTITY_MAP.get((column.entity or "").upper()) if column.entity else None
    period_end = column.period_end
    duration = column.duration_months
    comparison = _COMPARISON_MAP.get((column.comparison_role or "").upper()) if column.comparison_role else None

    # Stock statements: duration must stay None even if a spurious duration phrase binds.
    hint = observation.statement_hint
    if hint == "BALANCE_SHEET":
        duration = None

    dimension = label_dimension_hint(observation.row_label) or concept_dimension(None)
    row_decls = row_unit_declarations(
        observation.row_label, owner=f"row:{observation.row_index}", page=observation.source_ref.page_number
    )
    col_decls = list(column.unit_declarations)
    if column.currency or column.scale_factor is not None:
        from cse_financial_etl.compiler.units import UnitDeclaration, SCOPE_COLUMN

        # Synthetic column decl when compile_header already resolved currency/scale on the column.
        if column.currency is not None or column.scale_factor is not None:
            col_decls = list(col_decls) + [
                UnitDeclaration(
                    scope=SCOPE_COLUMN,
                    owner=column.column_id,
                    text=" | ".join(column.path) if column.path else column.column_id,
                    currency=column.currency,
                    scale=column.scale_factor,
                    scale_explicit=column.scale_explicit,
                    page=observation.source_ref.page_number,
                )
            ]
    unit_res = resolve_unit(
        dimension if dimension in {MONETARY, PER_SHARE} else MONETARY,
        row=row_decls,
        column=col_decls,
        table=list(table_unit_decls or ()),
        page=list(page_unit_decls or ()),
    )

    currency = unit_res.currency or column.currency
    scale = unit_res.scale if unit_res.scale is not None else column.scale_factor
    unit_dim: UnitDimension | None = None
    if dimension == PER_SHARE or unit_res.dimension == PER_SHARE:
        unit_dim = UnitDimension.PER_SHARE
        # Per-share must not inherit statement thousands.
        if scale is not None and scale >= Decimal("1000"):
            scale = Decimal("1")
            reasons.append("PER_SHARE_SCALE_RESET")
    elif currency is not None or scale is not None:
        unit_dim = UnitDimension.MONETARY

    if entity is not None:
        reasons.append("ENTITY_FROM_V1_HEADER")
    if period_end is not None:
        reasons.append("PERIOD_FROM_V1_HEADER")
    if duration is not None:
        reasons.append("DURATION_FROM_V1_HEADER")
    elif hint == "BALANCE_SHEET" and period_end is not None:
        reasons.append("STOCK_DURATION_NOT_APPLICABLE")
    if comparison is not None:
        reasons.append("COMPARISON_FROM_V1_HEADER")
    if unit_dim is not None:
        reasons.append("UNIT_FROM_V1_HEADER")

    complete = (
        entity is not None
        and period_end is not None
        and comparison is not None
        and unit_dim is not None
        and observation.raw_value is not None
        and observation.source_ref.bbox is not None
    )
    # FLOW may have duration None (period-ended / YTD) — still "context known" but not quarter-eligible.
    if hint != "BALANCE_SHEET" and duration is None and period_end is not None:
        reasons.append("FLOW_DURATION_UNRESOLVED_OR_CUMULATIVE")

    if complete:
        reasons.append("CONTEXT_BRIDGED_SOURCE_OWNED")
        # Drop discovery-only when required admission fields are evidenced.
        reasons = [c for c in reasons if c not in {"DISCOVERY_ONLY", "CONTEXT_UNRESOLVED_PENDING_V2_VERIFY"}]
    else:
        if "DISCOVERY_ONLY" not in reasons:
            reasons.append("DISCOVERY_ONLY")
        if "CONTEXT_UNRESOLVED_PENDING_V2_VERIFY" not in reasons:
            reasons.append("CONTEXT_UNRESOLVED_PENDING_V2_VERIFY")

    return observation.model_copy(
        update={
            "entity_scope": entity,
            "period_end": period_end,
            "duration_months": duration,
            "comparison_role": comparison,
            "currency": currency,
            "monetary_scale": scale,
            "unit_dimension": unit_dim,
            "reason_codes": tuple(dict.fromkeys(reasons)),
            "evidence_notes": tuple(dict.fromkeys(notes)),
            "publishable": False,
        }
    )


def compile_table_columns(table: TableIR, statement_hint: str | None) -> dict[int, CompiledHeaderColumn]:
    v1_type = _V1_STATEMENT_TYPE.get(statement_hint or "", None)
    header = compile_header(table, statement_type=v1_type, known=None)
    columns = {col.col_idx: col for col in header.columns}
    return _fill_comparison_roles_among_dated(columns)


def _fill_comparison_roles_among_dated(
    columns: dict[int, CompiledHeaderColumn],
) -> dict[int, CompiledHeaderColumn]:
    """Assign CURRENT/COMPARATIVE from dated peers only.

    V1 ``_assign_roles`` clears an entire (entity, duration) block when any sibling
    lacks a full date (common for year-only comparative or Change/% columns). That
    left printed quarter columns with ``comparison_role=None`` and blocked admission.
    Here we never invent dates — we only order columns that already have ``period_end``.
    """

    groups: dict[tuple[object, ...], list[CompiledHeaderColumn]] = {}
    for col in columns.values():
        if col.period_end is None:
            continue
        if col.kind and col.kind.upper() in {"CHANGE", "NOTE", "ANNOTATION", "UNIT"}:
            continue
        groups.setdefault((col.entity, col.duration_months), []).append(col)

    updates: dict[int, CompiledHeaderColumn] = {}
    for members in groups.values():
        if not members:
            continue
        latest = max(c.period_end for c in members if c.period_end is not None)
        for col in members:
            if col.comparison_role is not None or col.period_end is None:
                continue
            role = "CURRENT" if col.period_end == latest else "COMPARATIVE"
            evidence = dict(col.evidence)
            evidence["comparison_role"] = {
                "source": "dated_peer_order_bridge",
                "source_owned": True,
                "role": role,
                "selected_date": col.period_end.isoformat(),
            }
            updates[col.col_idx] = CompiledHeaderColumn(
                column_id=col.column_id,
                entity=col.entity,
                comparison_role=role,
                duration_months=col.duration_months,
                period_end=col.period_end,
                path=col.path,
                col_idx=col.col_idx,
                kind=col.kind,
                period_start=col.period_start,
                temporal_type=col.temporal_type,
                currency=col.currency,
                scale_factor=col.scale_factor,
                scale_explicit=col.scale_explicit,
                annotation=col.annotation,
                unit_declarations=col.unit_declarations,
                evidence=evidence,
                conflicts=col.conflicts,
            )
    if not updates:
        return columns
    merged = dict(columns)
    merged.update(updates)
    return merged


def enrich_observations_with_header_context(
    observations: tuple[V1SourceObservation, ...],
    *,
    tables_by_id: dict[str, TableIR],
) -> tuple[V1SourceObservation, ...]:
    """Re-emit observations with per-column header context where available."""

    from cse_financial_etl.compiler.units import SCOPE_TABLE, UnitDeclaration

    out: list[V1SourceObservation] = []
    columns_cache: dict[str, dict[int, CompiledHeaderColumn]] = {}
    table_unit_cache: dict[str, list] = {}
    for obs in observations:
        table = tables_by_id.get(obs.table_id)
        if table is None:
            out.append(obs)
            continue
        hint = obs.statement_hint or statement_hint_from_titles(table.title_texts)
        cache_key = f"{obs.table_id}:{hint}"
        if cache_key not in columns_cache:
            columns_cache[cache_key] = compile_table_columns(table, hint)
        if obs.table_id not in table_unit_cache:
            decls: list = []
            for i, text in enumerate(table.title_texts or ()):
                decl = UnitDeclaration.from_text(
                    text,
                    scope=SCOPE_TABLE,
                    owner=f"title:{obs.table_id}:{i}",
                    page=obs.source_ref.page_number,
                )
                if decl is not None:
                    decls.append(decl)
            for line in getattr(table, "unit_lines", ()) or ():
                decl = UnitDeclaration.from_text(
                    getattr(line, "text", "") or "",
                    scope=SCOPE_TABLE,
                    owner=f"unit_line:{obs.table_id}:{getattr(line, 'row_idx', 0)}",
                    page=obs.source_ref.page_number,
                )
                if decl is not None:
                    decls.append(decl)
            table_unit_cache[obs.table_id] = decls
        column = columns_cache[cache_key].get(obs.col_index)
        bridged = bridge_observation_context(
            obs.model_copy(update={"statement_hint": hint}),
            table=table,
            column=column,
            table_unit_decls=table_unit_cache[obs.table_id],
        )
        out.append(bridged)
    return tuple(_apply_unanimous_table_header_context(out))


def _apply_unanimous_table_header_context(
    observations: list[V1SourceObservation],
) -> list[V1SourceObservation]:
    """Fill missing entity/period only when the same table already prints one unanimous value.

    Never invent COMPANY/BANK from the issuer. Multi-entity tables (Group+Company)
    stay unresolved on silent columns.
    """

    by_table: dict[str, list[int]] = {}
    for i, obs in enumerate(observations):
        by_table.setdefault(obs.table_id, []).append(i)

    out = list(observations)
    for _table_id, idxs in by_table.items():
        entities = {out[i].entity_scope for i in idxs if out[i].entity_scope is not None}
        periods = {out[i].period_end for i in idxs if out[i].period_end is not None}
        sole_entity = next(iter(entities)) if len(entities) == 1 else None
        sole_period = next(iter(periods)) if len(periods) == 1 else None
        if sole_entity is None and sole_period is None:
            continue
        for i in idxs:
            obs = out[i]
            entity = obs.entity_scope
            period = obs.period_end
            reasons = list(obs.reason_codes)
            notes = list(obs.evidence_notes)
            changed = False
            if entity is None and sole_entity is not None:
                entity = sole_entity
                reasons.append("ENTITY_FROM_TABLE_HEADER_UNANIMOUS")
                notes.append("table_unanimous_entity")
                changed = True
            if period is None and sole_period is not None:
                period = sole_period
                reasons.append("PERIOD_FROM_TABLE_HEADER_UNANIMOUS")
                notes.append("table_unanimous_period")
                changed = True
            if not changed:
                continue
            complete = (
                entity is not None
                and period is not None
                and obs.comparison_role is not None
                and obs.unit_dimension is not None
                and obs.raw_value is not None
                and obs.source_ref.bbox is not None
            )
            if complete:
                reasons.append("CONTEXT_BRIDGED_SOURCE_OWNED")
                reasons = [
                    c
                    for c in reasons
                    if c not in {"DISCOVERY_ONLY", "CONTEXT_UNRESOLVED_PENDING_V2_VERIFY"}
                ]
            out[i] = obs.model_copy(
                update={
                    "entity_scope": entity,
                    "period_end": period,
                    "reason_codes": tuple(dict.fromkeys(reasons)),
                    "evidence_notes": tuple(dict.fromkeys(notes)),
                }
            )
    return out
