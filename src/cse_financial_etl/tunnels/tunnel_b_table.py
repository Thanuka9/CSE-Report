"""Tunnel B — independent table reconstruction compiler (§27)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.compiler.known_context import KnownContext
from cse_financial_etl.document.document_ir import (
    from_legacy_document_ir,
    sha256_file,
)
from cse_financial_etl.documents import document_ir as legacy_ir
from cse_financial_etl.tunnels.common_financial_engine import apply_financial_engine


def run_tunnel_b(
    pdf_path: Path,
    *,
    known: KnownContext,
    period_end: date | None = None,
) -> dict[str, Any]:
    """Materially different structural path: pdfplumber-first reconstruction."""

    pages = legacy_ir._extract_pdfplumber_pages(pdf_path)
    quality = legacy_ir._quality(pages, "PDFPLUMBER_WORDS")
    legacy = legacy_ir.DocumentIR(
        source_path=str(pdf_path),
        pages=tuple(pages),
        quality=quality,
    )
    document = from_legacy_document_ir(
        legacy,
        source_method="tunnel_b:pdfplumber",
        source_sha256=sha256_file(pdf_path) if pdf_path.exists() else "",
    )
    statements, ledger, graph = apply_financial_engine(document, known, tunnel="B")
    return {
        "tunnel": "B",
        "document": document,
        "statements": statements,
        "ledger": ledger,
        "graph": graph,
        "report": {
            "pages": document.quality.page_count,
            "tokens": document.quality.token_count,
            "statements": len(statements),
            "candidates": len(ledger.entries),
            "method": document.quality.extraction_method,
        },
    }
