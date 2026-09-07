"""Compile CanonicalFinancialStatement objects from reconstructed tables (sections 13-14)."""

from __future__ import annotations

from decimal import Decimal

from cse_financial_etl.accounting.row_context import build_row_context, structural_boost
from cse_financial_etl.accounting.semantic_candidates import generate_concept_hypotheses
from cse_financial_etl.compiler.canonical_statement import (
    CanonicalFinancialStatement,
    StatementCell,
    StatementRow,
)
from cse_financial_etl.compiler.column_compiler import compile_columns
from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.compiler.structure_normalizer import (
    normalize_search_text,
    normalize_unit_declaration,
    parse_numeric,
)
from cse_financial_etl.document.document_ir import CanonicalDocumentIR, TableIR
from cse_financial_etl.document.logical_rows import build_logical_rows
from cse_financial_etl.document.region_detector import StatementRegion
from cse_financial_etl.document.table_reconstructor import reconstruct_tables


def compile_statements(
    document: CanonicalDocumentIR,
    regions: list[StatementRegion],
    known: KnownContext,
) -> list[CanonicalFinancialStatement]:
    document = reconstruct_tables(document)
    statements: list[CanonicalFinancialStatement] = []
    pages = {p.page_number: p for p in document.pages}
    for region in regions:
        if region.statement_type in {"COVER", "OTHER", "RELATED_PARTY"}:
            continue
        page_rows: list[StatementRow] = []
        columns = []
        unit_evidence: list[dict] = []
        for page_no in range(region.page_start, region.page_end + 1):
            page = pages.get(page_no)
            if page is None:
                continue
            # Unit declarations on page.
            for line in page.lines[:12]:
                currency, scale = normalize_unit_declaration(line.text)
                if currency or scale:
                    unit_evidence.append(
                        {
                            "page": page_no,
                            "text": line.text,
                            "currency": currency,
                            "scale": str(scale) if scale else None,
                        }
                    )
            for table in page.tables:
                header_texts = [
                    c.raw_text
                    for c in table.cells
                    if c.row_idx in table.header_rows and c.col_idx == 0
                ] or [line.text for line in page.lines[:5]]
                scale = Decimal(unit_evidence[-1]["scale"]) if unit_evidence and unit_evidence[-1].get("scale") else None
                currency = unit_evidence[-1]["currency"] if unit_evidence else "LKR"
                columns = compile_columns(table, header_texts, currency=currency, scale_factor=scale)
                page_rows.extend(_rows_from_table(table, page_no, region.statement_type, columns))
            if not page.tables:
                # Fallback: logical rows without explicit TableIR.
                logical = build_logical_rows(page)
                meta_rows = [(f"p{page_no}-r{i}", r.normalized_label, r.indentation_level) for i, r in enumerate(logical)]
                for i, logical_row in enumerate(logical):
                    ctx = build_row_context(meta_rows, i) if meta_rows else None
                    hyps = generate_concept_hypotheses(
                        logical_row.raw_label,
                        statement_type=region.statement_type,
                        structural_score=structural_boost(ctx, "PAT") if ctx else 0.0,
                    )
                    # Attach numerics from last source line.
                    cells: dict[str, StatementCell] = {}
                    for line in logical_row.source_lines:
                        for tok_i, token in enumerate(line.tokens):
                            value = parse_numeric(token.text)
                            if value is None and not any(ch.isdigit() for ch in token.text):
                                continue
                            if value is None:
                                continue
                            col_id = f"c{tok_i + 1}"
                            cells[col_id] = StatementCell(
                                raw_text=token.text,
                                raw_numeric=value,
                                normalized_value=value * (scale or Decimal("1")) if scale else value,
                                source_page=page_no,
                                source_bbox=token.bbox,
                                column_id=col_id,
                            )
                    page_rows.append(
                        StatementRow(
                            row_id=f"p{page_no}-r{i}",
                            raw_label=logical_row.raw_label,
                            normalized_label=normalize_search_text(logical_row.raw_label),
                            indentation_level=logical_row.indentation_level,
                            parent_section=ctx.parent_section if ctx else None,
                            cells=cells,
                            hypotheses=hyps,
                        )
                    )
        if not page_rows:
            continue
        statements.append(
            CanonicalFinancialStatement(
                issuer_id=known.issuer_id,
                source_sha256=document.source_sha256,
                statement_type=region.statement_type,
                columns=columns,
                rows=page_rows,
                unit_evidence=unit_evidence,
                compilation_evidence={
                    "region_confidence": region.confidence,
                    "region_evidence": region.evidence,
                },
                page_start=region.page_start,
                page_end=region.page_end,
            )
        )
    return statements


def _rows_from_table(
    table: TableIR,
    page_no: int,
    statement_type: str,
    columns: list,
) -> list[StatementRow]:
    by_row: dict[int, list] = {}
    for cell in table.cells:
        by_row.setdefault(cell.row_idx, []).append(cell)
    scale = None
    for col in columns:
        if col.scale_factor is not None:
            scale = col.scale_factor
            break
    rows: list[StatementRow] = []
    meta = []
    for row_idx in sorted(by_row):
        cells = by_row[row_idx]
        label_cell = next((c for c in cells if c.col_idx == 0), None)
        label = label_cell.raw_text if label_cell else ""
        meta.append((f"p{page_no}-t{row_idx}", normalize_search_text(label), 0))
    for row_idx in sorted(by_row):
        cells = by_row[row_idx]
        label_cell = next((c for c in cells if c.col_idx == 0), None)
        label = label_cell.raw_text if label_cell else ""
        idx = sorted(by_row).index(row_idx)
        ctx = build_row_context(meta, idx) if meta else None
        hyps = []
        for hyp in generate_concept_hypotheses(label, statement_type=statement_type):
            boost = structural_boost(ctx, hyp.concept) if ctx else 0.0
            if boost:
                hyps.extend(
                    generate_concept_hypotheses(
                        label,
                        statement_type=statement_type,
                        structural_score=boost,
                    )
                )
                break
            hyps.append(hyp)
        cell_map: dict[str, StatementCell] = {}
        for cell in cells:
            if cell.col_idx == 0:
                continue
            value = parse_numeric(cell.raw_text)
            col_id = f"c{cell.col_idx}"
            cell_map[col_id] = StatementCell(
                raw_text=cell.raw_text,
                raw_numeric=value,
                normalized_value=(value * scale) if value is not None and scale else value,
                source_page=page_no,
                source_bbox=cell.bbox,
                column_id=col_id,
            )
        rows.append(
            StatementRow(
                row_id=f"p{page_no}-t{row_idx}",
                raw_label=label,
                normalized_label=normalize_search_text(label),
                indentation_level=0,
                parent_section=ctx.parent_section if ctx else None,
                cells=cell_map,
                hypotheses=hyps,
            )
        )
    return rows
