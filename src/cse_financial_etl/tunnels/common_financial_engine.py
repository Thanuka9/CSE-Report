"""Shared financial intelligence applied after independent structural readings.

Ledger candidates carry exactly what the document says. Missing entity, period,
duration or role stays ``None`` — the arbiter's eligibility contract rejects the
candidate instead of silently filling the gap from expected context. Statement-region
classification confidence is also preserved so a numeric-density guess can aid
discovery without independently authorizing publication.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from cse_financial_etl.compiler.canonical_statement import CanonicalFinancialStatement
from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.compiler.statement_compiler import compile_statements
from cse_financial_etl.compiler.statement_detector import detect_statements
from cse_financial_etl.compiler.units import PERCENT, concept_dimension
from cse_financial_etl.constraints.graph import build_constraint_graph
from cse_financial_etl.constraints.subtotal_discovery import discover_subtotals
from cse_financial_etl.document.document_ir import CanonicalDocumentIR
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry

FLOW_STATEMENTS = {"PROFIT_LOSS", "COMPREHENSIVE_INCOME", "SHARE_INFORMATION", "FINANCIAL_HIGHLIGHTS", "NOTES"}


def _column_header_conflicts(
    statement: CanonicalFinancialStatement,
    column_id: str,
) -> list[str]:
    """Return statement-level header conflicts owned by one numeric column."""

    owned: list[str] = []
    for conflict in statement.header_conflicts:
        text = str(conflict)
        if text.startswith(f"{column_id}:") or f":{column_id}:" in text:
            owned.append(text)
    return owned


def _statement_confidence(statement: CanonicalFinancialStatement) -> float | None:
    """Return the detector confidence that established the statement region."""

    raw = statement.compilation_evidence.get("region_confidence")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def apply_financial_engine(
    document: CanonicalDocumentIR,
    known: KnownContext,
    *,
    tunnel: str,
    statements: list[CanonicalFinancialStatement] | None = None,
) -> tuple[list[CanonicalFinancialStatement], CandidateLedger, object]:
    if statements is None:
        regions = detect_statements(document)
        statements = compile_statements(document, regions, known)
    graph = build_constraint_graph(statements)
    ledger = CandidateLedger()
    entry_i = 0
    for statement in statements:
        _ = discover_subtotals(statement)
        region_confidence = _statement_confidence(statement)
        for row in statement.rows:
            if not row.hypotheses:
                continue
            for col in statement.columns:
                if col.kind != "VALUE":
                    continue
                cell = row.cells.get(col.column_id)
                if cell is None or cell.raw_numeric is None:
                    continue
                for hyp in row.hypotheses:
                    dimension = concept_dimension(hyp.concept)
                    if dimension == PERCENT:
                        continue
                    value = cell.value_for(dimension)
                    unit = cell.unit_for(dimension) or {}
                    entry_i += 1
                    reasons: list[str] = []
                    if unit.get("status") != "RESOLVED":
                        reasons.append("UNIT_UNRESOLVED:" + ",".join(unit.get("reasons", []) or ["no_unit_evidence"]))
                    if col.entity is None:
                        reasons.append("ENTITY_UNKNOWN")
                    if col.period_end is None:
                        reasons.append("PERIOD_UNKNOWN")
                    if col.comparison_role is None:
                        reasons.append("ROLE_UNKNOWN")
                    if statement.statement_type in FLOW_STATEMENTS and col.duration_months is None:
                        reasons.append("DURATION_UNKNOWN")
                    if region_confidence is None:
                        reasons.append("STATEMENT_REGION_CONFIDENCE_UNKNOWN")
                    elif region_confidence < 0.80:
                        reasons.append(f"STATEMENT_REGION_WEAK:{region_confidence:.3f}")
                    for conflict in col.conflicts:
                        reasons.append(f"HEADER_CONFLICT:{conflict}")
                    for conflict in _column_header_conflicts(statement, col.column_id):
                        reasons.append(f"HEADER_CONFLICT:{conflict}")
                    ledger.add(
                        LedgerEntry(
                            entry_id=f"{tunnel}-{entry_i}",
                            tunnel=tunnel,
                            concept=hyp.concept,
                            status="unresolved",
                            raw_value=cell.raw_numeric,
                            normalized_value=value,
                            entity=col.entity,
                            period_end=col.period_end.isoformat() if col.period_end else None,
                            duration_months=(col.duration_months if statement.statement_type in FLOW_STATEMENTS else None),
                            comparison_role=col.comparison_role,
                            unit=unit.get("currency"),
                            scale_factor=_scale_int(unit.get("scale")),
                            page=cell.source_page,
                            bbox=str(cell.source_bbox),
                            label=row.raw_label,
                            score=hyp.total_score,
                            reasons=reasons,
                            evidence={
                                "candidate_origin": "compiler_geometry",
                                "statement_type": statement.statement_type,
                                "statement_region_confidence": region_confidence,
                                "statement_region_evidence": statement.compilation_evidence.get("region_evidence"),
                                "statement_region_type": statement.compilation_evidence.get("region_statement_type"),
                                "table_index": statement.table_index,
                                "row_id": row.row_id,
                                "column_id": col.column_id,
                                "column_path": list(col.context_evidence_ids),
                                "column_evidence": col.evidence,
                                "temporal_type": col.temporal_type,
                                "annotation": col.annotation,
                                "dimension": dimension,
                                "unit_resolution": unit,
                                "semantic_score": hyp.semantic_score,
                                "hypotheses": [(h.concept, h.total_score) for h in row.hypotheses[:5]],
                                "semantic_evidence": list(hyp.evidence),
                                "source_line_ids": list(row.source_line_ids),
                                "header_conflicts": list(statement.header_conflicts),
                            },
                        )
                    )
    return statements, ledger, graph


def _scale_int(scale: Any) -> int | None:
    if scale is None:
        return None
    try:
        value = Decimal(str(scale))
    except Exception:
        return None
    if value == value.to_integral_value():
        return int(value)
    return None
