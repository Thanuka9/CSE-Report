from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from cse_financial_etl.document.region_detector import detect_regions
from cse_financial_etl.extraction.statement_extractor import extract_filing
from cse_financial_etl.ingestion.quality_router import route_document_ingestion
from cse_financial_etl.tunnels.tunnel_a_geometry import run_tunnel_a
from tests.fixture_paths import real_pdf


def _entry_debug(entry: object) -> dict[str, object]:
    return {
        "entry_id": getattr(entry, "entry_id", None),
        "tunnel": getattr(entry, "tunnel", None),
        "status": getattr(entry, "status", None),
        "raw_value": str(getattr(entry, "raw_value", None)),
        "normalized_value": str(getattr(entry, "normalized_value", None)),
        "entity": getattr(entry, "entity", None),
        "period_end": getattr(entry, "period_end", None),
        "duration_months": getattr(entry, "duration_months", None),
        "comparison_role": getattr(entry, "comparison_role", None),
        "unit": getattr(entry, "unit", None),
        "scale_factor": getattr(entry, "scale_factor", None),
        "page": getattr(entry, "page", None),
        "label": getattr(entry, "label", None),
        "score": getattr(entry, "score", None),
        "reasons": getattr(entry, "reasons", None),
        "evidence": getattr(entry, "evidence", None),
    }


def _statement_debug(statement: object) -> dict[str, object]:
    rows = []
    for row in getattr(statement, "rows", []):
        label = str(getattr(row, "raw_label", ""))
        if "operat" not in label.casefold() and "profit" not in label.casefold():
            continue
        rows.append(
            {
                "row_id": getattr(row, "row_id", None),
                "raw_label": label,
                "hypotheses": [
                    {
                        "concept": getattr(hyp, "concept", None),
                        "semantic_score": getattr(hyp, "semantic_score", None),
                        "total_score": getattr(hyp, "total_score", None),
                        "evidence": getattr(hyp, "evidence", None),
                    }
                    for hyp in getattr(row, "hypotheses", [])
                ],
                "cells": {
                    key: {
                        "raw": getattr(cell, "raw_text", None),
                        "raw_numeric": str(getattr(cell, "raw_numeric", None)),
                    }
                    for key, cell in getattr(row, "cells", {}).items()
                },
            }
        )
    return {
        "statement_type": getattr(statement, "statement_type", None),
        "page_start": getattr(statement, "page_start", None),
        "page_end": getattr(statement, "page_end", None),
        "table_index": getattr(statement, "table_index", None),
        "compilation_evidence": getattr(statement, "compilation_evidence", None),
        "rows": rows,
    }


def test_commercial_bank_operating_profit_candidate_survives_extraction() -> None:
    pdf = real_pdf("2026-06-30_369_1786618965674.pdf")
    facts = extract_filing(
        pdf,
        "COMMERCIAL BANK OF CEYLON PLC",
        "COMB.N0000",
        date(2026, 6, 30),
        ocr_enabled=False,
    )
    candidates = [fact for fact in facts if fact.metric_code == "OPERATING_PROFIT"]
    if any(
        fact.normalized_value == Decimal("29495553000")
        and fact.status == "EXTRACTED"
        for fact in candidates
    ):
        return

    document = route_document_ingestion(pdf, ocr_enabled=False)
    regions = [
        {
            "type": region.statement_type,
            "page_start": region.page_start,
            "page_end": region.page_end,
            "confidence": region.confidence,
            "evidence": region.evidence,
        }
        for region in detect_regions(document)
        if region.page_start <= 7 <= region.page_end
    ]
    tunnel = run_tunnel_a(
        pdf,
        issuer_name="COMMERCIAL BANK OF CEYLON PLC",
        symbol="COMB.N0000",
        period_end=date(2026, 6, 30),
        ocr_enabled=False,
        legacy_facts=None,
        document=document,
        compile_statements=True,
    )
    native = [
        _entry_debug(entry)
        for entry in tunnel["ledger"].for_concept("OPERATING_PROFIT")
        if getattr(entry, "evidence", {}).get("candidate_origin") == "compiler_geometry"
    ]
    statements = [
        _statement_debug(statement)
        for statement in tunnel["statements"]
        if getattr(statement, "page_start", None) == 7
        or any(
            "operat" in str(getattr(row, "raw_label", "")).casefold()
            for row in getattr(statement, "rows", [])
        )
    ]
    raise AssertionError(
        json.dumps(
            {
                "published": [fact.as_json() for fact in candidates],
                "page7_regions": regions,
                "native": native,
                "statements": statements,
            },
            indent=2,
            default=str,
        )
    )
