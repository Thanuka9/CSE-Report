"""Tunnel A — native geometry financial compiler (primary path, §26)."""

from __future__ import annotations

import json
from contextlib import suppress
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

# Layout-assist candidates remain discovery aids and are capped below native compiler
# evidence. Target issuer/period metadata may constrain a query, but it is bridged into a
# ledger candidate only when the layout extractor independently corroborated the selected
# row with high-confidence PDF geometry. Ambiguous rows stay unresolved.
_LAYOUT_ASSIST_CAP = 0.45
_LAYOUT_CONTEXT_MIN_ENTITY_CONFIDENCE = 0.90
_LAYOUT_CONTEXT_MIN_PERIOD_CONFIDENCE = 0.90
_LAYOUT_CONTEXT_MIN_COLUMN_CONFIDENCE = 0.80
_LAYOUT_CONTEXT_MIN_CANDIDATE_MARGIN = 0.10


def _confidence(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _period_string(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    text = str(value).strip()
    return text or None


def _layout_candidate_competition_resolved(evidence: dict[str, Any]) -> bool:
    """Reject a layout bridge when another different value is an evidence near-tie."""

    rows = evidence.get("candidate_scores")
    if not isinstance(rows, list) or not rows:
        return False
    selected = next(
        (
            row
            for row in rows
            if isinstance(row, dict) and row.get("selected") is True
        ),
        None,
    )
    if not isinstance(selected, dict):
        return False
    try:
        selected_score = float(selected.get("score"))
    except (TypeError, ValueError):
        return False
    selected_raw = str(selected.get("raw_value") or "").replace(",", "").strip()
    if not selected_raw:
        return False
    for row in rows:
        if not isinstance(row, dict) or row is selected:
            continue
        raw = str(row.get("raw_value") or "").replace(",", "").strip()
        if not raw or raw == selected_raw:
            continue
        try:
            score = float(row.get("score"))
        except (TypeError, ValueError):
            return False
        if selected_score - score < _LAYOUT_CONTEXT_MIN_CANDIDATE_MARGIN:
            return False
    return True


def _layout_entity_structure_resolved(
    *,
    entity: str,
    entity_confidence: float,
    evidence: dict[str, Any],
) -> bool:
    """Require structural ownership for the 0.94 dual-entity confidence tier."""

    # 0.95+ is produced by an explicit standalone statement/entity title. 0.94 is the
    # extractor's dual-entity tier and must additionally prove a real multi-column block.
    if entity_confidence >= 0.95:
        return True
    if entity_confidence < 0.93:
        return False
    graph = evidence.get("graph")
    if not isinstance(graph, dict):
        return False
    clusters = graph.get("cluster_centers")
    parent_kind = str(evidence.get("entity_parent_kind") or "").strip().upper()
    return (
        isinstance(clusters, list)
        and len(clusters) >= 4
        and parent_kind == entity
    )


def _source_corroborated_layout_context(
    fact: Any,
) -> tuple[str | None, str | None, str | None, dict[str, Any]]:
    """Bridge target context only after the PDF row independently corroborates it.

    The legacy layout extractor receives target issuer/period metadata, so those fields
    cannot be treated as source evidence merely because they appear on ``ExtractedFact``.
    However, an ``EXTRACTED``/``PASSED`` row also carries source-derived entity confidence,
    comparison-role geometry, duration, column ownership, candidate competition and a
    page/line/bbox reference. Only when all of those agree may trusted target metadata be
    attached to the candidate. Ambiguous values remain fail-closed.
    """

    status = str(getattr(fact, "status", "") or "").strip().upper()
    validation_status = str(
        getattr(fact, "validation_status", "") or ""
    ).strip().upper()
    source_page = getattr(fact, "source_page", None)
    source_line = str(getattr(fact, "source_line", "") or "").strip()
    source_bbox = str(getattr(fact, "source_bbox", "") or "").strip()
    has_geometry_reference = (
        source_page is not None and bool(source_line) and bool(source_bbox)
    )

    raw_evidence = getattr(fact, "evidence_json", None)
    evidence: dict[str, Any] = {}
    if raw_evidence:
        try:
            loaded = json.loads(str(raw_evidence))
            if isinstance(loaded, dict):
                evidence = loaded
        except (TypeError, ValueError, json.JSONDecodeError):
            evidence = {}

    entity = str(getattr(fact, "entity_scope", "") or "").strip().upper()
    comparison_role = str(
        getattr(fact, "comparison_role", "") or ""
    ).strip().upper()
    evidence_role = str(evidence.get("comparison_role") or "").strip().upper()
    period_end = _period_string(getattr(fact, "period_end", None))
    duration_months = getattr(fact, "duration_months", None)
    evidence_duration = evidence.get("duration_months")
    parent_kind = str(evidence.get("entity_parent_kind") or "").strip().upper()
    entity_confidence = _confidence(getattr(fact, "entity_confidence", 0.0))
    period_confidence = _confidence(getattr(fact, "period_confidence", 0.0))
    column_confidence = _confidence(getattr(fact, "column_confidence", 0.0))

    base_ok = (
        status == "EXTRACTED"
        and validation_status == "PASSED"
        and has_geometry_reference
    )
    entity_structure_ok = _layout_entity_structure_resolved(
        entity=entity,
        entity_confidence=entity_confidence,
        evidence=evidence,
    )
    entity_ok = (
        base_ok
        and entity in {"COMPANY", "BANK", "GROUP"}
        and entity_confidence >= _LAYOUT_CONTEXT_MIN_ENTITY_CONFIDENCE
        and entity_structure_ok
        and not (
            entity in {"COMPANY", "BANK"}
            and parent_kind in {"GROUP", "CONSOLIDATED"}
        )
    )
    column_ok = column_confidence >= _LAYOUT_CONTEXT_MIN_COLUMN_CONFIDENCE
    competition_ok = _layout_candidate_competition_resolved(evidence)
    role_ok = (
        base_ok
        and column_ok
        and comparison_role == "CURRENT"
        and evidence_role == "CURRENT"
        and period_confidence >= _LAYOUT_CONTEXT_MIN_PERIOD_CONFIDENCE
    )

    # Flow rows must preserve exact-quarter duration. Stock rows legitimately have no
    # duration. If evidence explicitly records a duration, it must agree with the fact.
    duration_ok = duration_months in {None, 3}
    if evidence_duration is not None:
        if duration_months is None:
            duration_ok = False
        else:
            try:
                duration_ok = duration_ok and int(evidence_duration) == int(duration_months)
            except (TypeError, ValueError):
                duration_ok = False

    period_ok = role_ok and duration_ok and period_end is not None
    bridge_ok = entity_ok and period_ok and competition_ok

    corroboration = {
        "bridge_eligible": bridge_ok,
        "status": status,
        "validation_status": validation_status,
        "has_geometry_reference": has_geometry_reference,
        "entity": entity_ok,
        "entity_structure": entity_structure_ok,
        "target_period": period_ok,
        "comparison_role": role_ok,
        "column_identity": column_ok,
        "candidate_competition": competition_ok,
        "duration": duration_ok,
        "entity_confidence": entity_confidence,
        "period_confidence": period_confidence,
        "column_confidence": column_confidence,
    }
    if not bridge_ok:
        return None, None, None, corroboration
    return entity, period_end, "CURRENT", corroboration


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

    Layout extractor facts may assist discovery as ledger candidates. They are never
    allowed to turn requested target context into observed evidence without independent
    PDF corroboration; arbiter + query + final validation remain mandatory.
    """

    if known is None:
        try:
            entity = infer_entity_scope(issuer_name)
        except Exception:
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
    """Inject layout discoveries while preserving a fail-closed context boundary.

    High-confidence rows may bridge trusted target metadata only when their own PDF
    geometry independently corroborates entity and CURRENT-period ownership. Everything
    else keeps those dimensions unresolved. The bridge remains a low-score candidate and
    must still pass the same arbiter, target query and final-validator contracts.
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

        semantic_confidence = getattr(fact, "semantic_confidence", None)
        fact_period = getattr(fact, "period_end", None)
        bridged_entity, bridged_period, bridged_role, corroboration = (
            _source_corroborated_layout_context(fact)
        )
        evidence: dict[str, Any] = {
            "candidate_origin": "layout_geometry",
            "extraction_method": getattr(fact, "extraction_method", "LAYOUT_TEXT"),
            "layout_status": status,
            "semantic_model": getattr(fact, "semantic_model", ""),
            "overall_certainty": getattr(fact, "overall_certainty", 0.0),
            "legacy_target_period": (
                fact_period.isoformat()
                if fact_period is not None and hasattr(fact_period, "isoformat")
                else str(fact_period or "")
            ),
            "legacy_entity_scope": getattr(fact, "entity_scope", None),
            "legacy_comparison_role": getattr(fact, "comparison_role", None),
            "legacy_duration_months": getattr(fact, "duration_months", None),
            # The target period/entity originate in trusted run metadata, not the PDF.
            # This flag remains True even for bridged rows; the corroboration object
            # records the independent PDF evidence that permits the bridge.
            "context_not_source_owned": True,
            "source_context_corroboration": corroboration,
        }
        if semantic_confidence is not None:
            with suppress(TypeError, ValueError):
                evidence["semantic_score"] = float(semantic_confidence)

        reasons = [f"legacy_status:{status}", "layout_assist"]
        if corroboration["bridge_eligible"]:
            reasons.append("layout_context_corroborated_by_pdf")
        else:
            reasons.extend(
                [
                    "ENTITY_UNKNOWN:layout_source_evidence_insufficient",
                    "PERIOD_UNKNOWN:layout_source_evidence_insufficient",
                    "ROLE_UNKNOWN:layout_source_evidence_insufficient",
                ]
            )

        ledger.add(
            LedgerEntry(
                entry_id=f"{tunnel}-layout-{index}",
                tunnel=tunnel,
                concept=getattr(fact, "metric_code", "UNKNOWN"),
                status=ledger_status,
                raw_value=getattr(fact, "raw_value", None),
                normalized_value=getattr(fact, "normalized_value", None),
                entity=bridged_entity,
                period_end=bridged_period,
                duration_months=getattr(fact, "duration_months", None),
                comparison_role=bridged_role,
                unit=getattr(fact, "currency", None),
                scale_factor=getattr(fact, "scale_factor", None),
                page=getattr(fact, "source_page", None),
                bbox=getattr(fact, "source_bbox", None),
                label=getattr(fact, "raw_label", None) or getattr(fact, "source_line", None),
                score=score,
                reasons=reasons,
                evidence=evidence,
            )
        )
