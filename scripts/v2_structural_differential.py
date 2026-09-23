"""R5 structural differential: compare V1 vs V2 discovery counts on the same PDF.

Diagnostic only. Does not retune extraction or promote engines.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from cse_financial_etl.document.document_ir import from_legacy_document_ir
from cse_financial_etl.document.region_detector import detect_regions
from cse_financial_etl.document.table_reconstructor import reconstruct_page_tables
from cse_financial_etl.documents.document_ir import extract_document_ir
from cse_financial_etl.v2.document.router import read_document
from cse_financial_etl.v2.statements.detector import detect_statement_regions
from cse_financial_etl.v2.statements.table_reconstructor import reconstruct_statements


def _v1_counts(pdf: Path) -> dict:
    try:
        legacy = extract_document_ir(pdf)
        document = from_legacy_document_ir(legacy, source_sha256="0" * 64)
    except Exception as exc:  # noqa: BLE001 - diagnostic harness
        return {"error": str(exc)}
    regions = detect_regions(document)
    tables = 0
    cells = 0
    for page in document.pages:
        page_tables = reconstruct_page_tables(page)
        tables += len(page_tables)
        cells += sum(len(table.cells) for table in page_tables)
    return {
        "pages": len(document.pages),
        "statement_regions": len(regions),
        "tables": tables,
        "cells": cells,
    }


def _v2_counts(pdf: Path, filing_version_id: str) -> dict:
    document = read_document(pdf, filing_version_id=filing_version_id)
    regions = detect_statement_regions(document)
    statements = reconstruct_statements(document, regions)
    rows = sum(len(statement.rows) for statement in statements)
    cells = sum(len(row.cells) for statement in statements for row in statement.rows)
    return {
        "pages": len(document.pages),
        "statement_regions": len(regions),
        "statements": len(statements),
        "rows": rows,
        "cells": cells,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--filing-version-id", required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/v2/universe/r5_structural_differential.json"),
    )
    args = parser.parse_args()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pdf": str(args.pdf).replace("\\", "/"),
        "filing_version_id": args.filing_version_id,
        "v1": _v1_counts(args.pdf),
        "v2": _v2_counts(args.pdf, args.filing_version_id),
        "note": (
            "Diagnostic structural counts only. Port generalized winners after review; "
            "do not issuer-patch. Production remains engine=v1 / floor 8924."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if args.out.is_file():
        existing = json.loads(args.out.read_text(encoding="utf-8"))
    filings = list(existing.get("filings", []))
    filings = [row for row in filings if row.get("filing_version_id") != args.filing_version_id]
    filings.append(payload)
    report = {
        "id": "r5-structural-differential",
        "recovery_step": "R5",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "filings": filings,
        "hard_rules": [
            "Do not promote V2",
            "Do not lower 8924",
            "Port only generalized techniques",
        ],
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
