"""Shared financial intelligence applied after independent structural readings."""

from __future__ import annotations

from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.compiler.statement_compiler import compile_statements
from cse_financial_etl.compiler.statement_detector import detect_statements
from cse_financial_etl.constraints.graph import build_constraint_graph
from cse_financial_etl.constraints.subtotal_discovery import discover_subtotals
from cse_financial_etl.document.document_ir import CanonicalDocumentIR
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry


def apply_financial_engine(
    document: CanonicalDocumentIR,
    known: KnownContext,
    *,
    tunnel: str,
) -> tuple[list, CandidateLedger, object]:
    regions = detect_statements(document)
    statements = compile_statements(document, regions, known)
    graph = build_constraint_graph(statements)
    ledger = CandidateLedger()
    entry_i = 0
    for statement in statements:
        _ = discover_subtotals(statement)  # evidence retained; concepts from row hypotheses
        for row in statement.rows:
            for hyp in row.hypotheses:
                for col in statement.columns or []:
                    cell = row.cells.get(col.column_id)
                    if cell is None or cell.raw_numeric is None:
                        continue
                    entry_i += 1
                    ledger.add(
                        LedgerEntry(
                            entry_id=f"{tunnel}-{entry_i}",
                            tunnel=tunnel,
                            concept=hyp.concept,
                            status="unresolved",
                            raw_value=cell.raw_numeric,
                            normalized_value=cell.normalized_value,
                            entity=col.entity or known.required_entity,
                            period_end=col.period_end.isoformat() if col.period_end else known.target_period_end.isoformat(),
                            duration_months=col.duration_months
                            if statement.statement_type
                            in {"PROFIT_LOSS", "COMPREHENSIVE_INCOME", "SHARE_INFORMATION"}
                            else None,
                            comparison_role=col.comparison_role or "CURRENT",
                            unit=col.currency,
                            scale_factor=int(col.scale_factor) if col.scale_factor is not None else None,
                            page=cell.source_page,
                            bbox=str(cell.source_bbox),
                            label=row.raw_label,
                            score=hyp.total_score,
                            evidence={
                                "statement_type": statement.statement_type,
                                "hypotheses": [h.concept for h in row.hypotheses[:5]],
                            },
                        )
                    )
                # No columns compiled — still emit label-level unresolved candidates from first numeric cell.
                if not statement.columns:
                    for col_id, cell in row.cells.items():
                        if cell.raw_numeric is None:
                            continue
                        entry_i += 1
                        ledger.add(
                            LedgerEntry(
                                entry_id=f"{tunnel}-{entry_i}",
                                tunnel=tunnel,
                                concept=hyp.concept,
                                status="unresolved",
                                raw_value=cell.raw_numeric,
                                normalized_value=cell.normalized_value,
                                entity=known.required_entity,
                                period_end=known.target_period_end.isoformat(),
                                duration_months=known.target_duration_months
                                if statement.statement_type
                                in {"PROFIT_LOSS", "COMPREHENSIVE_INCOME"}
                                else None,
                                comparison_role="CURRENT",
                                unit="LKR",
                                scale_factor=None,
                                page=cell.source_page,
                                bbox=str(cell.source_bbox),
                                label=row.raw_label,
                                score=hyp.total_score,
                                evidence={"statement_type": statement.statement_type, "column_id": col_id},
                            )
                        )
    return statements, ledger, graph
