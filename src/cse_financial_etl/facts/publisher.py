"""Publish ExtractedFact rows from compiler query results (sections 36-41, 57).

Layout discovery may seed ledger candidates. Publication always flows through
arbiter -> target query -> final gates. Silent layout-only publish is forbidden.

Every published fact carries four separate provenance fields in ``evidence_json``
(audit finding 2):

* ``publication_routing`` — which path produced the row
  (``statement_compiler`` | ``layout_assist_only`` | ``explicit_layout_fallback``).
* ``extraction_origin`` — where the selected evidence actually came from
  (``compiler_geometry`` | ``tunnel_b`` | ``layout_geometry`` | ``eps_selection_policy``).
* ``native_compiler_success`` — whether the native statement compiler produced
  compiled statements for this filing (never True when compiled statements == 0).
* ``explicit_fallback`` — issue code when a bounded fallback was used, else ``None``.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

from cse_financial_etl.contracts.eligibility import FinalCheck
from cse_financial_etl.facts.query_engine import QueriedFact
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry
from cse_financial_etl.validation.final_validator import validate_source_fact

if TYPE_CHECKING:
    from cse_financial_etl.extraction.statement_extractor import ExtractedFact

# Explicit issue codes for bounded layout fallback (never silent).
LAYOUT_FALLBACK_COMPILER_EXCEPTION = "LAYOUT_FALLBACK_COMPILER_EXCEPTION"
LAYOUT_FALLBACK_QUERY_MISS = "LAYOUT_FALLBACK_QUERY_MISS"
LAYOUT_FALLBACK_GATE_FAIL = "LAYOUT_FALLBACK_GATE_FAIL"
COMPILER_DISABLED = "COMPILER_DISABLED"
COMPILER_NO_STATEMENTS = "COMPILER_NO_STATEMENTS"

ROUTING_STATEMENT_COMPILER = "statement_compiler"
ROUTING_LAYOUT_ASSIST_ONLY = "layout_assist_only"
ROUTING_EXPLICIT_FALLBACK = "explicit_layout_fallback"

# Machine output never carries a human approval (audit finding 6).
MACHINE_REVIEW_STATUS = "REVIEW"


def compiler_routing(report: dict[str, Any]) -> tuple[str, bool, str | None]:
    """Return ``(publication_routing, native_compiler_success, explicit_fallback)``."""

    tunnel_a = report.get("tunnel_a") or {}
    compiled = int(tunnel_a.get("statements") or 0)
    requested = bool(tunnel_a.get("compile_requested", True))
    if compiled > 0:
        return ROUTING_STATEMENT_COMPILER, True, None
    if not requested:
        return ROUTING_LAYOUT_ASSIST_ONLY, False, COMPILER_DISABLED
    return ROUTING_LAYOUT_ASSIST_ONLY, False, COMPILER_NO_STATEMENTS


def publish_from_compiler(
    *,
    queried: list[QueriedFact],
    layout_facts: list[Any],
    report: dict[str, Any],
    issuer_name: str,
    symbol: str,
    period_end: date,
    required_entity: str,
    target_duration: int = 3,
) -> tuple[list[Any], dict[str, Any]]:
    """Build the official fact list from compiler queries, not raw layout rows."""

    routing, native_ok, fallback_code = compiler_routing(report)
    layout_by_code = {f.metric_code: f for f in layout_facts}
    queried_by_code = {q.metric_code: q for q in queried}
    published: list[ExtractedFact] = []
    stats: dict[str, Any] = {
        "publication_routing": routing,
        "native_compiler_success": native_ok,
        "explicit_fallback": fallback_code,
        "compiler_selected": 0,
        "layout_assist_selected": 0,
        "tunnel_b_selected": 0,
        "explicit_layout_fallback": 0,
        "terminal_unresolved": 0,
        "final_check_failures": 0,
        "fallback_issue_codes": [],
    }

    skip_projection = {"EPS_SELECTED", "CROSS_METRIC_CONTEXT"}
    codes = [c for c in dict.fromkeys([*layout_by_code.keys(), *queried_by_code.keys()]) if c not in skip_projection]
    for code in codes:
        layout = layout_by_code.get(code)
        queried_fact = queried_by_code.get(code)
        if queried_fact is None:
            if layout is None:
                continue
            published.append(
                _explicit_fallback_fact(
                    layout,
                    report=report,
                    issue_code=LAYOUT_FALLBACK_QUERY_MISS,
                    detail="metric_absent_from_compiler_query",
                )
            )
            stats["explicit_layout_fallback"] += 1
            stats["fallback_issue_codes"].append(f"{code}:{LAYOUT_FALLBACK_QUERY_MISS}")
            continue

        check = validate_source_fact(
            queried_fact.entry,
            required_entity=required_entity,
            target_duration=target_duration,
            target_period_end=period_end.isoformat(),
            concept=queried_fact.concept,
        )
        if queried_fact.status == "EXTRACTED" and queried_fact.entry is not None:
            if queried_fact.entry.normalized_value is None or check.status == "FAIL":
                stats["final_check_failures"] += 1
                published.append(
                    _from_terminal(
                        queried_fact,
                        layout,
                        report=report,
                        issuer_name=issuer_name,
                        symbol=symbol,
                        period_end=period_end,
                        override_status="VALUE_CONTEXT_UNRESOLVED",
                        issue=check.detail if check.status == "FAIL" else "accepted_without_value",
                        check=check,
                    )
                )
                stats["terminal_unresolved"] += 1
                continue
            origin = _candidate_origin(queried_fact.entry)
            published.append(
                _from_accepted_entry(
                    queried_fact,
                    layout,
                    report=report,
                    issuer_name=issuer_name,
                    symbol=symbol,
                    period_end=period_end,
                    check=check,
                )
            )
            if origin == "layout_geometry":
                stats["layout_assist_selected"] += 1
            elif origin == "tunnel_b":
                stats["tunnel_b_selected"] += 1
            else:
                stats["compiler_selected"] += 1
            continue

        published.append(
            _from_terminal(
                queried_fact,
                layout,
                report=report,
                issuer_name=issuer_name,
                symbol=symbol,
                period_end=period_end,
                check=check,
            )
        )
        stats["terminal_unresolved"] += 1

    published.extend(
        _project_eps_selected(
            published,
            layout_by_code=layout_by_code,
            report=report,
            issuer_name=issuer_name,
            symbol=symbol,
            period_end=period_end,
            required_entity=required_entity,
        )
    )

    selected_total = stats["compiler_selected"] + stats["layout_assist_selected"] + stats["tunnel_b_selected"]
    report_stats = {
        **stats,
        "layout_assist_rate": stats["layout_assist_selected"] / max(1, selected_total),
        "explicit_fallback_rate": stats["explicit_layout_fallback"] / max(1, len(published)),
    }
    return published, report_stats


def _project_eps_selected(
    published: list[Any],
    *,
    layout_by_code: dict[str, Any],
    report: dict[str, Any],
    issuer_name: str,
    symbol: str,
    period_end: date,
    required_entity: str,
) -> list[Any]:
    from cse_financial_etl.extraction.statement_extractor import (
        ExtractedFact,
        _selected_eps_fact,
    )

    routing, native_ok, fallback_code = compiler_routing(report)
    by_code = {f.metric_code: f for f in published}
    selected = _selected_eps_fact(
        issuer_name,
        symbol,
        period_end,
        required_entity,
        diluted=by_code.get("EPS_DILUTED"),
        basic=by_code.get("EPS_BASIC"),
        navps=by_code.get("NAVPS"),
    )
    evidence: dict[str, Any] = {}
    if selected.evidence_json:
        try:
            evidence = json.loads(selected.evidence_json)
        except json.JSONDecodeError:
            evidence = {"prior": selected.evidence_json}
    evidence.update(
        _provenance(
            routing=routing,
            origin="eps_selection_policy",
            native_ok=native_ok,
            fallback=fallback_code,
            report=report,
        )
    )
    projected = ExtractedFact(
        issuer_name=selected.issuer_name,
        symbol=selected.symbol,
        period_end=selected.period_end,
        metric_code=selected.metric_code,
        metric_type=selected.metric_type,
        raw_text=selected.raw_text,
        raw_value=selected.raw_value,
        normalized_value=selected.normalized_value,
        currency=selected.currency,
        scale_factor=selected.scale_factor,
        entity_scope=selected.entity_scope,
        source_page=selected.source_page,
        source_line=selected.source_line,
        unit_source_text=selected.unit_source_text,
        confidence=selected.confidence,
        status=selected.status,
        raw_label=selected.raw_label,
        source_bbox=selected.source_bbox,
        extraction_method="COMPILER_QUERY",
        semantic_model=selected.semantic_model,
        semantic_confidence=selected.semantic_confidence,
        entity_confidence=selected.entity_confidence,
        period_confidence=selected.period_confidence,
        unit_confidence=selected.unit_confidence,
        column_confidence=selected.column_confidence,
        validation_confidence=selected.validation_confidence,
        overall_certainty=selected.overall_certainty,
        certainty_band=selected.certainty_band,
        comparison_role=selected.comparison_role,
        duration_months=selected.duration_months,
        validation_status=selected.validation_status,
        review_status=MACHINE_REVIEW_STATUS,
        evidence_json=json.dumps(evidence, default=str),
    )
    extras = [projected]
    layout_cross = layout_by_code.get("CROSS_METRIC_CONTEXT")
    if layout_cross is not None:
        extras.append(
            _explicit_fallback_fact(
                layout_cross,
                report=report,
                issue_code=LAYOUT_FALLBACK_QUERY_MISS,
                detail="cross_metric_context_from_layout_diagnostics",
            )
        )
    return extras


def mark_explicit_layout_fallback(
    layout_facts: list[Any],
    *,
    issue_code: str,
    detail: str,
    report: dict[str, Any] | None = None,
) -> list[Any]:
    """Last-resort publish path — always issue-coded, never silent."""

    return [
        _explicit_fallback_fact(fact, report=report or {}, issue_code=issue_code, detail=detail)
        for fact in layout_facts
    ]


def _candidate_origin(entry: LedgerEntry) -> str:
    origin = entry.evidence.get("candidate_origin")
    if isinstance(origin, str) and origin:
        return origin
    if entry.tunnel == "A" and "legacy_status" in " ".join(entry.reasons):
        return "layout_geometry"
    if entry.tunnel == "A":
        return "compiler_geometry"
    return f"tunnel_{entry.tunnel.lower()}"


def _provenance(
    *,
    routing: str,
    origin: str | None,
    native_ok: bool,
    fallback: str | None,
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        # legacy key kept for readers; identical to publication_routing
        "publication_path": routing,
        "publication_routing": routing,
        "extraction_origin": origin,
        "native_compiler_success": native_ok,
        "explicit_fallback": fallback,
        "compiler_report_summary": {
            "filing_sha": report.get("filing_sha"),
            "tunnel_a": report.get("tunnel_a"),
            "tunnel_b": report.get("tunnel_b"),
            "resolver_c": report.get("resolver_c"),
            "no_overpublication_violations": report.get("no_overpublication_violations"),
            "publication_stats": report.get("publication_stats"),
        },
    }


def _evidence_blob(
    *,
    report: dict[str, Any],
    routing: str,
    candidate_origin: str | None,
    native_ok: bool,
    fallback: str | None,
    issue_code: str | None = None,
    detail: str | None = None,
    prior: str | None = None,
    entry: LedgerEntry | None = None,
    check: FinalCheck | None = None,
    queried: QueriedFact | None = None,
    prior_validation_status: str | None = None,
) -> str:
    evidence: dict[str, Any] = {}
    if prior:
        try:
            evidence = json.loads(prior)
        except json.JSONDecodeError:
            evidence = {"prior": prior}
    evidence.update(
        _provenance(routing=routing, origin=candidate_origin, native_ok=native_ok, fallback=fallback, report=report)
    )
    if issue_code:
        evidence["issue_code"] = issue_code
        evidence["explicit_fallback"] = issue_code
    if detail:
        evidence["issue_detail"] = detail
    if entry is not None:
        evidence["ledger_entry_id"] = entry.entry_id
        evidence["ledger_tunnel"] = entry.tunnel
        evidence["ledger_reasons"] = list(entry.reasons)
        evidence["ledger_score"] = entry.score
        evidence["source_evidence"] = {
            "page": entry.page,
            "bbox": entry.bbox,
            "label": entry.label,
            "column_id": entry.evidence.get("column_id"),
            "column_path": entry.evidence.get("column_path"),
            "unit_resolution": entry.evidence.get("unit_resolution"),
            "dimension": entry.evidence.get("dimension"),
            "corroborated_by": entry.evidence.get("corroborated_by"),
        }
    if check is not None:
        evidence["final_check"] = {"status": check.status, "detail": check.detail, "reasons": list(check.reasons)}
    if prior_validation_status is not None:
        evidence["prior_validation_status"] = prior_validation_status
    if queried is not None:
        evidence["query_status"] = queried.status
        evidence["query_issue"] = queried.issue
        evidence["eligibility_reasons"] = list(queried.eligibility_reasons)
        if queried.trace is not None:
            evidence["search_trace"] = queried.trace.as_dict()
    return json.dumps(evidence, default=str)


def _metric_type(layout: Any | None, concept: str) -> str:
    if layout is not None:
        return str(layout.metric_type)
    if concept in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}:
        return "MONETARY_PER_SHARE"
    if concept in {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES"}:
        return "STOCK"
    return "FLOW"


def _validation_status(check: FinalCheck, layout: Any | None, origin: str) -> str:
    """Never upgrade a preserved FAILED to PASSED without an explicit revalidation."""

    if check.status == "FAIL":
        return "FAILED"
    prior = getattr(layout, "validation_status", None) if layout is not None else None
    if origin == "layout_geometry" and prior in {"FAILED", "REJECTED"}:
        # The selected evidence *is* the layout fact that previously failed; the source
        # check alone does not revalidate the cross-metric failure it recorded.
        return "FAILED"
    if check.status == "PASS":
        return "PASSED"
    return "NOT_VALIDATED"


def _from_accepted_entry(
    queried: QueriedFact,
    layout: Any | None,
    *,
    report: dict[str, Any],
    issuer_name: str,
    symbol: str,
    period_end: date,
    check: FinalCheck,
) -> Any:
    from cse_financial_etl.extraction.statement_extractor import ExtractedFact

    entry = queried.entry
    assert entry is not None
    # Entity is mandatory for every accepted source fact. Comparison role is
    # mandatory only for exact-quarter FLOW concepts and is already enforced by
    # the shared eligibility contract; AS_AT stock facts do not need a role.
    assert entry.entity is not None
    origin = _candidate_origin(entry)
    routing, native_ok, fallback_code = compiler_routing(report)
    unit_resolution = entry.evidence.get("unit_resolution") or {}
    unit_text = None
    if isinstance(unit_resolution, dict):
        owners = [unit_resolution.get("currency_owner"), unit_resolution.get("scale_owner")]
        unit_text = " | ".join(str(o) for o in owners if o)
    if not unit_text and layout is not None and origin == "layout_geometry":
        unit_text = layout.unit_source_text
    validation_status = _validation_status(check, layout, origin)
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=queried.metric_code,
        metric_type=_metric_type(layout, queried.concept),
        raw_text=str(entry.raw_value) if entry.raw_value is not None else (layout.raw_text if layout else None),
        raw_value=entry.raw_value if entry.raw_value is not None else (layout.raw_value if layout else None),
        normalized_value=entry.normalized_value,
        currency=entry.unit,
        scale_factor=entry.scale_factor,
        entity_scope=entry.entity,
        source_page=entry.page,
        source_line=entry.label,
        unit_source_text=unit_text,
        confidence=layout.confidence if layout and origin == "layout_geometry" else "HIGH",
        status="EXTRACTED",
        raw_label=entry.label,
        source_bbox=entry.bbox,
        extraction_method="COMPILER_QUERY",
        semantic_model=layout.semantic_model if layout and origin == "layout_geometry" else "compiler",
        semantic_confidence=float(entry.evidence.get("semantic_score", entry.score)),
        entity_confidence=layout.entity_confidence if layout and origin == "layout_geometry" else 1.0,
        period_confidence=layout.period_confidence if layout and origin == "layout_geometry" else 1.0,
        unit_confidence=layout.unit_confidence if layout and origin == "layout_geometry" else 1.0,
        column_confidence=layout.column_confidence if layout and origin == "layout_geometry" else 1.0,
        validation_confidence=1.0 if check.status == "PASS" else 0.0,
        overall_certainty=float(entry.score),
        certainty_band=layout.certainty_band if layout and origin == "layout_geometry" else "HIGH",
        comparison_role=entry.comparison_role,
        duration_months=entry.duration_months,
        validation_status=validation_status,
        review_status=MACHINE_REVIEW_STATUS,
        evidence_json=_evidence_blob(
            report=report,
            routing=routing,
            candidate_origin=origin,
            native_ok=native_ok,
            fallback=fallback_code,
            prior=layout.evidence_json if layout else None,
            entry=entry,
            check=check,
            queried=queried,
            prior_validation_status=getattr(layout, "validation_status", None) if layout else None,
        ),
    )


def _from_terminal(
    queried: QueriedFact,
    layout: Any | None,
    *,
    report: dict[str, Any],
    issuer_name: str,
    symbol: str,
    period_end: date,
    override_status: str | None = None,
    issue: str | None = None,
    check: FinalCheck | None = None,
) -> Any:
    from cse_financial_etl.extraction.statement_extractor import ExtractedFact

    status = override_status or queried.status
    entry = queried.entry
    routing, native_ok, fallback_code = compiler_routing(report)
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=queried.metric_code,
        metric_type=_metric_type(layout, queried.concept),
        raw_text=str(entry.raw_value) if entry is not None and entry.raw_value is not None else None,
        raw_value=entry.raw_value if entry is not None else None,
        normalized_value=None,  # never publish a value on a non-EXTRACTED row
        currency=entry.unit if entry is not None else None,
        scale_factor=entry.scale_factor if entry is not None else None,
        entity_scope=(entry.entity if entry and entry.entity else None) or (layout.entity_scope if layout else "UNKNOWN"),
        source_page=entry.page if entry and entry.page is not None else (layout.source_page if layout else None),
        source_line=entry.label if entry and entry.label else (layout.source_line if layout else None),
        unit_source_text=None,
        confidence="LOW",
        status=status,
        raw_label=entry.label if entry else (layout.raw_label if layout else None),
        source_bbox=entry.bbox if entry else (layout.source_bbox if layout else None),
        extraction_method="COMPILER_QUERY",
        semantic_model="compiler",
        semantic_confidence=0.0,
        entity_confidence=0.0,
        period_confidence=0.0,
        unit_confidence=0.0,
        column_confidence=0.0,
        validation_confidence=0.0,
        overall_certainty=0.0,
        certainty_band="NONE",
        comparison_role=entry.comparison_role if entry and entry.comparison_role else "UNKNOWN",
        duration_months=entry.duration_months if entry and entry.duration_months is not None else None,
        validation_status="FAILED" if check is not None and check.status == "FAIL" else "NOT_VALIDATED",
        review_status=MACHINE_REVIEW_STATUS,
        evidence_json=_evidence_blob(
            report=report,
            routing=routing,
            candidate_origin=_candidate_origin(entry) if entry else None,
            native_ok=native_ok,
            fallback=fallback_code,
            issue_code=None,
            detail=issue or queried.issue,
            prior=layout.evidence_json if layout else None,
            entry=entry,
            check=check,
            queried=queried,
            prior_validation_status=getattr(layout, "validation_status", None) if layout else None,
        ),
    )


def _explicit_fallback_fact(
    layout: Any,
    *,
    report: dict[str, Any],
    issue_code: str,
    detail: str,
) -> Any:
    from cse_financial_etl.extraction.statement_extractor import ExtractedFact

    _, native_ok, _ = compiler_routing(report) if report else (ROUTING_EXPLICIT_FALLBACK, False, issue_code)
    return ExtractedFact(
        issuer_name=layout.issuer_name,
        symbol=layout.symbol,
        period_end=layout.period_end,
        metric_code=layout.metric_code,
        metric_type=layout.metric_type,
        raw_text=layout.raw_text,
        raw_value=layout.raw_value,
        normalized_value=layout.normalized_value,
        currency=layout.currency,
        scale_factor=layout.scale_factor,
        entity_scope=layout.entity_scope,
        source_page=layout.source_page,
        source_line=layout.source_line,
        unit_source_text=layout.unit_source_text,
        confidence=layout.confidence,
        status=layout.status,
        raw_label=layout.raw_label,
        source_bbox=layout.source_bbox,
        extraction_method="LAYOUT_FALLBACK",
        semantic_model=layout.semantic_model,
        semantic_confidence=layout.semantic_confidence,
        entity_confidence=layout.entity_confidence,
        period_confidence=layout.period_confidence,
        unit_confidence=layout.unit_confidence,
        column_confidence=layout.column_confidence,
        validation_confidence=layout.validation_confidence,
        overall_certainty=layout.overall_certainty,
        certainty_band=layout.certainty_band,
        comparison_role=layout.comparison_role,
        duration_months=layout.duration_months,
        validation_status=layout.validation_status,
        review_status=MACHINE_REVIEW_STATUS,
        evidence_json=_evidence_blob(
            report=report,
            routing=ROUTING_EXPLICIT_FALLBACK,
            candidate_origin="layout_geometry",
            native_ok=native_ok,
            fallback=issue_code,
            issue_code=issue_code,
            detail=detail,
            prior=layout.evidence_json,
            prior_validation_status=layout.validation_status,
        ),
    )
