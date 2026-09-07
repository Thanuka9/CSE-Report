"""Tunnel A — native geometry financial compiler (primary path, §26)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.accounting.sector_profiles import profile_for_issuer
from cse_financial_etl.compiler.known_context import KnownContext, build_known_context
from cse_financial_etl.config import infer_entity_scope
from cse_financial_etl.ingestion.quality_router import route_document_ingestion
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.tunnels.common_financial_engine import apply_financial_engine


def run_tunnel_a(
    pdf_path: Path,
    *,
    issuer_name: str,
    symbol: str,
    period_end: date,
    ocr_enabled: bool = False,
    ocr_dir: Path | None = None,
    known: KnownContext | None = None,
    legacy_facts: list[Any] | None = None,
) -> dict[str, Any]:
    """Primary compiler. Incorporates mature layout extraction as accepted seed candidates."""

    if known is None:
        try:
            entity = infer_entity_scope(issuer_name)
        except Exception:
            entity = "COMPANY"
        profile = profile_for_issuer(issuer_name)
        known = build_known_context(
            issuer_name=issuer_name,
            symbol=symbol,
            period_end=period_end,
            required_entity=entity,
            sector_profile=profile.code,
        )
    if legacy_facts is not None:
        # Fast publication path: seed ledger from layout extractor; skip second PDF parse.
        from cse_financial_etl.document.document_ir import (
            CanonicalDocumentIR,
            DocumentQuality,
            sha256_file,
        )
        from cse_financial_etl.resolution.candidate_ledger import CandidateLedger

        digest = ""
        try:
            # Hash is required for lineage; skip only if file missing.
            if pdf_path.exists():
                digest = sha256_file(pdf_path)
        except OSError:
            digest = ""
        document = CanonicalDocumentIR(
            pages=(),
            quality=DocumentQuality(
                page_count=0,
                token_count=0,
                numeric_token_count=0,
                text_page_ratio=1.0,
                extraction_method="LEGACY_SEEDED",
                requires_ocr=False,
            ),
            source_sha256=digest,
            source_path=str(pdf_path),
        )
        ledger = CandidateLedger()
        _seed_from_legacy(ledger, legacy_facts, tunnel="A")
        return {
            "tunnel": "A",
            "document": document,
            "statements": [],
            "ledger": ledger,
            "graph": None,
            "known": known,
            "report": {
                "pages": 0,
                "tokens": 0,
                "statements": 0,
                "candidates": len(ledger.entries),
                "method": "LEGACY_SEEDED",
                "mode": "legacy_seeded",
            },
        }
    document = route_document_ingestion(pdf_path, ocr_enabled=ocr_enabled, ocr_dir=ocr_dir)
    statements, ledger, graph = apply_financial_engine(document, known, tunnel="A")
    return {
        "tunnel": "A",
        "document": document,
        "statements": statements,
        "ledger": ledger,
        "graph": graph,
        "known": known,
        "report": {
            "pages": document.quality.page_count,
            "tokens": document.quality.token_count,
            "statements": len(statements),
            "candidates": len(ledger.entries),
            "method": document.quality.extraction_method,
            "mode": "full_compiler",
        },
    }


def _seed_from_legacy(ledger: CandidateLedger, facts: list[Any], *, tunnel: str) -> None:
    for index, fact in enumerate(facts, start=1):
        status = getattr(fact, "status", "")
        ledger_status = "accepted" if status in {"EXTRACTED", "EXTRACTED_DERIVED"} else (
            "rejected" if status in {"CUMULATIVE_ONLY"} else "unresolved"
        )
        if status in {
            "NOT_FOUND_BY_PARSER",
            "VALUE_CONTEXT_UNRESOLVED",
            "SOURCE_CONFIRMED_NOT_REPORTED",
            "EXACT_QUARTER_NOT_REPORTED",
            "UNIT_NOT_RESOLVED",
            "LOW_CERTAINTY",
            "INSUFFICIENT_INPUT",
        }:
            # Keep terminal legacy misses visible without inventing numbers.
            ledger_status = "rejected" if status == "CUMULATIVE_ONLY" else "unresolved"
            if getattr(fact, "normalized_value", None) is None and status.startswith("SOURCE_"):
                ledger_status = "rejected"
        ledger.add(
            LedgerEntry(
                entry_id=f"{tunnel}-legacy-{index}",
                tunnel=tunnel,
                concept=getattr(fact, "metric_code", "UNKNOWN"),
                status=ledger_status if getattr(fact, "normalized_value", None) is not None else (
                    "rejected" if status in {"SOURCE_CONFIRMED_NOT_REPORTED", "CUMULATIVE_ONLY"} else "unresolved"
                ),
                raw_value=getattr(fact, "raw_value", None),
                normalized_value=getattr(fact, "normalized_value", None),
                entity=getattr(fact, "entity_scope", None),
                period_end=getattr(fact, "period_end", date.today()).isoformat()
                if hasattr(getattr(fact, "period_end", None), "isoformat")
                else str(getattr(fact, "period_end", "")),
                duration_months=getattr(fact, "duration_months", None),
                comparison_role=getattr(fact, "comparison_role", "CURRENT"),
                unit=getattr(fact, "currency", None),
                scale_factor=getattr(fact, "scale_factor", None),
                page=getattr(fact, "source_page", None),
                bbox=getattr(fact, "source_bbox", None),
                label=getattr(fact, "raw_label", None) or getattr(fact, "source_line", None),
                score=float(getattr(fact, "overall_certainty", 0.0) or getattr(fact, "semantic_confidence", 0.0) or 0.85),
                reasons=[f"legacy_status:{status}"],
                evidence={"extraction_method": getattr(fact, "extraction_method", "LAYOUT_TEXT")},
            )
        )
