"""Whole-document context map for review cases (Phase One Milestone 2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cse_financial_etl.documents.document_ir import DocumentIR


def build_document_context(document: DocumentIR) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    for page in document.pages:
        head = " ".join(line.text for line in page.lines[:12])
        pages.append(
            {
                "page": page.number,
                "width": page.width,
                "height": page.height,
                "token_count": sum(len(line.tokens) for line in page.lines),
                "line_count": len(page.lines),
                "numeric_token_count": sum(len(line.numeric_tokens) for line in page.lines),
                "head": head[:400],
            }
        )
    quality = document.quality
    return {
        "page_count": len(document.pages),
        "extraction_method": quality.extraction_method,
        "ocr_used": quality.ocr_used,
        "quality": document.evidence_dict(),
        "pages": pages,
    }


def write_document_context(diagnostics_dir: Path, document: DocumentIR) -> Path:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    path = diagnostics_dir / "document_context.json"
    path.write_text(
        json.dumps(build_document_context(document), indent=2),
        encoding="utf-8",
    )
    return path
