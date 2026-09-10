"""Tunnel A — native geometry financial compiler (primary path, §26)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.accounting.sector_profiles import profile_for_issuer
from cse_financial_etl.compiler.known_context import KnownContext, build_known_context
from cse_financial_etl.config import infer_entity_scope
from cse_financial_etl.document.document_ir import CanonicalDocumentIR
from cse_financial_etl.ingestion.quality_router import route_document_ingestion
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger, LedgerEntry
from cse_financial_etl.tunnels.common_financial_engine import apply_financial_engine

# Layout-assist candidates are discovery aids: their score is derived from the layout
# extractor's own certainty and capped below any compiler candidate with a regex-anchored
# label match (1.0 semantic) so they can never outrank real compiled evidence.
_LAYOUT_ASSIST_CAP = 0.45


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
    document: CanonicalDocumentIR | None = None,
    compile_statements: bool = True,
) -> dict[str, Any]:
    """Primary compiler.

    Layout extractor facts may assist discovery as ledger candidates. They are
    never pre-accepted for publication — arbiter + query remain mandatory.
    """

    if known is None:
        try:
            entity = infer_entity_scope(issuer_name)
        except Exception:
            # Inference/configuration failure is an unresolved dimension, not proof
            # that the filing is a standalone company statement.
            entity = "UNKNOWN"
        profile = profile_for_issuer(issuer_name)
        known = build_known_context(
            issuer_name=issuer_name,
            symbol=symbol,
            period_end=period_end,
            required_entity=entity,
            sector_profile=profile.code,
        )

    statements: list[Any] = []
    graph: Any = None
    ledger = CandidateLedger()
    mode = "full_compiler"

    if document is not None:
        working_doc = document
    elif compile_statements:
        working_doc = route_document_ingestion(
            pdf_path, ocr_enabled=ocr_enabled, ocr_dir=ocr_dir
        )
    else:
        working_doc = _empty_document(pdf_path)
        mode = "layout_assist_only"

    if compile_statements and working_doc.pages:
        statements, ledger, graph = apply_financial_engine(
            working_doc, known, tunnel="A"
        )
        mode = "full_compiler"

    if legacy_facts is not None:
        _seed_layout_assist(ledger, legacy_facts, tunnel="A")
        mode = (
            "full_compiler_with_layout_assist"
            if statements or (working_doc.pages and compile_statements)
            else "layout_assist_compiler"
        )

    return {
        "tunnel": "A",
        "document": working_doc,
        "statements": statements,
        "ledger": ledger,
        "graph": graph,
        "known": known,
        "report": {
            "pages": working_doc.quality.page_count,
            "tokens": working_doc.quality.token_count,
            "statements": len(statements),
            "compiled_statement_types": sorted({s.statement_type for s in statements}),
            "candidates": len(ledger.entries),
            "method": working_doc.quality.extraction_method,
            "mode": mode,
            "compile_requested": bool(compile_statements),
            "native_compiler_success": bool(statements),
            "layout_assist_candidates": sum(
                1
                for e in ledger.entries
                if e.evidence.get("candidate_origin") == "layout_geometry"
            ),
        },
    }


def _empty_document(pdf_path: Path) -> CanonicalDocumentIR:
    from cse_financial_etl.document.document_ir import DocumentQuality, sha256_file

    digest = ""
    try:
        if pdf_path.exists():
            digest = sha256_file(pdf_path)
    except OSError:
        digest = ""
    return CanonicalDocumentIR(
        pages=(),
        quality=DocumentQuality(
            page_count=0,
            token_count=0,
            numeric_token_count=0,
            text_page_ratio=1.0,
            extraction_method="LAYOUT_ASSIST_ONLY",
            requires_ocr=False,
        ),
        source_sha256=digest,
        source_path=str(pdf_path),
    )


def _seed_layout_assist(ledger: CandidateLedger, facts: list[Any], *, tunnel: str) -> None:
    """Inject layout discoveries as unresolved candidates (not pre-published).

    Preserve the layout extractor's semantic evidence.  The shared eligibility
    contract is responsible for deciding whether a discovered row is semantically
    strong enough to publish; dropping that score here previously allowed weak
    RapidFuzz guesses to bypass LABEL_EVIDENCE_WEAK when they were the only candidate.
    Missing dimensions stay missing — especially comparison role; this bridge must
    never manufacture CURRENT merely because an older fact object lacks that field.
    """

    for index, fact in enumerate(facts, start=1):
        status = getattr(fact, "status", "")
        has_value = getattr(fact, "normalized_value", None) is not None
        if status in {"EXTRACTED", "EXTRACTED_DERIVED"} and has_value:
            ledger_status = "unresolved"
            certainty = float(getattr(fact, "overall_certainty", 0.0) or 0.0)
            score = min(_LAYOUT_ASSIST_CAP, max(0.1, certainty * _LAYOUT_ASSIST_CAP))
        elif status == "CUMULATIVE_ONLY":
            ledger_status = "rejected"
            score = 0.2
        elif status in {
            "SOURCE_CONFIRMED_NOT_REPORTED",
            "EXACT_QUARTER_NOT_REPORTED",
            "NOT_FOUND_BY_PARSER",
            "VALUE_CONTEXT_UNRESOLVED",
            "UNIT_NOT_RESOLVED",
            "LOW_CERTAINTY",
            "INSUFFICIENT_INPUT",
            "CONSOLIDATED_ONLY",
        }:
            ledger_status = "rejected" if not has_value else "unresolved"
            score = 0.1
        else:
            ledger_status = "unresolved" if has_value else "rejected"
            score = min(
                _LAYOUT_ASSIST_CAP,
                float(
                    getattr(fact, "overall_certainty", 0.0)
                    or getattr(fact, "semantic_confidence", 0.0)
                    or (0.4 if has_value else 0.1)
                )
                * _LAYOUT_ASSIST_CAP,
            )

        period = getattr(fact, "period_end", None)
        period_s = period.isoformat() if period is not None and hasattr(period, "isoformat") else (str(period) if period else None)
        semantic_confidence = getattr(fact, "semantic_confidence", None)
        evidence: dict[str, Any] = {
            "candidate_origin": "layout_geometry",
            "extraction_method": getattr(fact, "extraction_method", "LAYOUT_TEXT"),
            "layout_status": status,
            "semantic_model": getattr(fact, "semantic_model", ""),
            "overall_certainty": getattr(fact, "overall_certainty", 0.0),
        }
        if semantic_confidence is not None:
            try:
                evidence["semantic_score"] = float(semantic_confidence)
            except (TypeError, ValueError):
                pass

        role = getattr(fact, "comparison_role", None)
        if role is not None:
            role = str(role).strip().upper() or None

        ledger.add(
            LedgerEntry(
                entry_id=f"{tunnel}-layout-{index}",
                tunnel=tunnel,
                concept=getattr(fact, "metric_code", "UNKNOWN"),
                status=ledger_status,
                raw_value=getattr(fact, "raw_value", None),
                normalized_value=getattr(fact, "normalized_value", None),
                entity=getattr(fact, "entity_scope", None),
                period_end=period_s,
                duration_months=getattr(fact, "duration_months", None),
                comparison_role=role,
                unit=getattr(fact, "currency", None),
                scale_factor=getattr(fact, "scale_factor", None),
                page=getattr(fact, "source_page", None),
                bbox=getattr(fact, "source_bbox", None),
                label=getattr(fact, "raw_label", None) or getattr(fact, "source_line", None),
                score=score,
                reasons=[f"legacy_status:{status}", "layout_assist"],
                evidence=evidence,
            )
        )
