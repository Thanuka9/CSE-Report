"""Publish ExtractedFact rows from compiler query results (sections 36-41, 57).

Layout discovery may seed ledger candidates. Publication always flows through
arbiter -> target query -> final gates. Silent layout-only publish is forbidden.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

from cse_financial_etl.facts.query_engine import QueriedFact
from cse_financial_etl.resolution.candidate_ledger import LedgerEntry
from cse_financial_etl.validation.final_validator import FinalCheck, validate_source_fact

if TYPE_CHECKING:
    from cse_financial_etl.extraction.statement_extractor import ExtractedFact

# Explicit issue codes for bounded layout fallback (never silent).
LAYOUT_FALLBACK_COMPILER_EXCEPTION = "LAYOUT_FALLBACK_COMPILER_EXCEPTION"
LAYOUT_FALLBACK_QUERY_MISS = "LAYOUT_FALLBACK_QUERY_MISS"
LAYOUT_FALLBACK_GATE_FAIL = "LAYOUT_FALLBACK_GATE_FAIL"
COMPILER_DISABLED = "COMPILER_DISABLED"


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

    layout_by_code = {f.metric_code: f for f in layout_facts}
    queried_by_code = {q.metric_code: q for q in queried}
    published: list[ExtractedFact] = []
    stats = {
        "publication_path": "statement_compiler",
        "compiler_selected": 0,
        "layout_assist_selected": 0,
        "explicit_layout_fallback": 0,
        "terminal_unresolved": 0,
        "fallback_issue_codes": [],
    }

    # Universe of metric codes the pipeline historically emits.
    skip_projection = {"EPS_SELECTED", "CROSS_METRIC_CONTEXT"}
    codes = [
        c
        for c in dict.fromkeys([*layout_by_code.keys(), *queried_by_code.keys()])
        if c not in skip_projection
    ]
    for code in codes:
        layout = layout_by_code.get(code)
        queried_fact = queried_by_code.get(code)
        if queried_fact is None:
            if layout is None:
                continue
            # Compiler query set omitted this metric — bounded explicit fallback.
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
        )
        if queried_fact.status == "EXTRACTED" and queried_fact.entry is not None:
            if queried_fact.entry.normalized_value is None or check.status == "FAIL":
                published.append(
                    _from_terminal(
                        queried_fact,
                        layout,
                        report=report,
                        issuer_name=issuer_name,
                        symbol=symbol,
                        period_end=period_end,
                        override_status="VALUE_CONTEXT_UNRESOLVED"
                        if check.status == "FAIL"
                        else (layout.status if layout else "NOT_FOUND_BY_PARSER"),
                        issue=check.detail if check.status == "FAIL" else "accepted_without_value",
                    )
                )
                stats["terminal_unresolved"] += 1
                continue
            origin = _candidate_origin(queried_fact.entry)
            fact = _from_accepted_entry(
                queried_fact,
                layout,
                report=report,
                issuer_name=issuer_name,
                symbol=symbol,
                period_end=period_end,
                check=check,
            )
            published.append(fact)
            if origin == "layout_geometry":
                stats["layout_assist_selected"] += 1
            else:
                stats["compiler_selected"] += 1
            continue

        # Terminal / unresolved compiler outcomes — prefer compiler status.
        published.append(
            _from_terminal(
                queried_fact,
                layout,
                report=report,
                issuer_name=issuer_name,
                symbol=symbol,
                period_end=period_end,
            )
        )
        if queried_fact.status in {"EXTRACTED", "EXTRACTED_DERIVED"}:
            stats["compiler_selected"] += 1
        else:
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

    report_stats = {
        **stats,
        "layout_assist_rate": (
            stats["layout_assist_selected"]
            / max(1, stats["compiler_selected"] + stats["layout_assist_selected"])
        ),
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
    evidence["publication_path"] = "statement_compiler"
    evidence["candidate_origin"] = "eps_selection_policy"
    evidence["compiler_report_summary"] = {
        "filing_sha": report.get("filing_sha"),
        "tunnel_a": report.get("tunnel_a"),
        "tunnel_b": report.get("tunnel_b"),
        "resolver_c": report.get("resolver_c"),
    }
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
        review_status=selected.review_status,
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
    return f"tunnel_{entry.tunnel.lower()}"


def _evidence_blob(
    *,
    report: dict[str, Any],
    publication_path: str,
    candidate_origin: str | None,
    issue_code: str | None = None,
    detail: str | None = None,
    prior: str | None = None,
    entry: LedgerEntry | None = None,
) -> str:
    evidence: dict[str, Any] = {}
    if prior:
        try:
            evidence = json.loads(prior)
        except json.JSONDecodeError:
            evidence = {"prior": prior}
    evidence["publication_path"] = publication_path
    if candidate_origin:
        evidence["candidate_origin"] = candidate_origin
    if issue_code:
        evidence["issue_code"] = issue_code
    if detail:
        evidence["issue_detail"] = detail
    evidence["compiler_report_summary"] = {
        "filing_sha": report.get("filing_sha"),
        "tunnel_a": report.get("tunnel_a"),
        "tunnel_b": report.get("tunnel_b"),
        "resolver_c": report.get("resolver_c"),
        "no_overpublication_violations": report.get("no_overpublication_violations"),
        "publication_stats": report.get("publication_stats"),
    }
    if entry is not None:
        evidence["ledger_entry_id"] = entry.entry_id
        evidence["ledger_tunnel"] = entry.tunnel
        evidence["ledger_reasons"] = list(entry.reasons)
    return json.dumps(evidence, default=str)


def _metric_type(layout: Any | None, concept: str) -> str:
    if layout is not None:
        return layout.metric_type
    if concept in {"EPS_BASIC", "EPS_DILUTED", "NAVPS"}:
        return "MONETARY_PER_SHARE"
    if concept in {"TOTAL_ASSETS", "TOTAL_EQUITY", "TOTAL_LIABILITIES", "NAVPS"}:
        return "STOCK"
    return "FLOW"


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
    origin = _candidate_origin(entry)
    # Prefer ledger values (compiler decision); fill presentation fields from layout when same origin.
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=queried.metric_code,
        metric_type=_metric_type(layout, queried.concept),
        raw_text=str(entry.raw_value) if entry.raw_value is not None else (layout.raw_text if layout else None),
        raw_value=entry.raw_value if entry.raw_value is not None else (layout.raw_value if layout else None),
        normalized_value=entry.normalized_value,
        currency=entry.unit or (layout.currency if layout else "LKR"),
        scale_factor=entry.scale_factor
        if entry.scale_factor is not None
        else (layout.scale_factor if layout else None),
        entity_scope=entry.entity or (layout.entity_scope if layout else "COMPANY"),
        source_page=entry.page if entry.page is not None else (layout.source_page if layout else None),
        source_line=entry.label or (layout.source_line if layout else None),
        unit_source_text=layout.unit_source_text if layout else None,
        confidence=layout.confidence if layout and origin == "layout_geometry" else "HIGH",
        status="EXTRACTED",
        raw_label=entry.label or (layout.raw_label if layout else None),
        source_bbox=entry.bbox or (layout.source_bbox if layout else None),
        extraction_method="COMPILER_QUERY",
        semantic_model=layout.semantic_model if layout and origin == "layout_geometry" else "compiler",
        semantic_confidence=float(entry.score),
        entity_confidence=layout.entity_confidence if layout else 0.9,
        period_confidence=layout.period_confidence if layout else 0.9,
        unit_confidence=layout.unit_confidence if layout else 0.9,
        column_confidence=layout.column_confidence if layout else 0.9,
        validation_confidence=1.0 if check.status == "PASS" else 0.5,
        overall_certainty=max(float(entry.score), layout.overall_certainty if layout else 0.0),
        certainty_band=layout.certainty_band if layout and origin == "layout_geometry" else "HIGH",
        comparison_role=entry.comparison_role or "CURRENT",
        duration_months=entry.duration_months
        if entry.duration_months is not None
        else (layout.duration_months if layout else None),
        validation_status="PASSED" if check.status == "PASS" else "NOT_VALIDATED",
        review_status=layout.review_status if layout else "REVIEW",
        evidence_json=_evidence_blob(
            report=report,
            publication_path="statement_compiler",
            candidate_origin=origin,
            prior=layout.evidence_json if layout else None,
            entry=entry,
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
) -> Any:
    from cse_financial_etl.extraction.statement_extractor import ExtractedFact

    status = override_status or queried.status
    entry = queried.entry
    if (
        layout is not None
        and override_status is None
        and status
        in {
            "NOT_FOUND_BY_PARSER",
            "VALUE_CONTEXT_UNRESOLVED",
            "CUMULATIVE_ONLY",
            "SOURCE_CONFIRMED_NOT_REPORTED",
            "EXACT_QUARTER_NOT_REPORTED",
            "UNIT_NOT_RESOLVED",
            "LOW_CERTAINTY",
            "INSUFFICIENT_INPUT",
        }
        and layout.status not in {"EXTRACTED", "EXTRACTED_DERIVED"}
    ):
        # Preserve richer layout terminal coding when compiler agrees it's unresolved.
        status = layout.status
    return ExtractedFact(
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        metric_code=queried.metric_code,
        metric_type=_metric_type(layout, queried.concept),
        raw_text=layout.raw_text if layout else None,
        raw_value=entry.raw_value if entry is not None else (layout.raw_value if layout else None),
        normalized_value=(
            entry.normalized_value if entry is not None else (layout.normalized_value if layout else None)
        ),
        currency=layout.currency if layout else None,
        scale_factor=layout.scale_factor if layout else None,
        entity_scope=(
            (entry.entity if entry and entry.entity else None)
            or (layout.entity_scope if layout else "COMPANY")
        ),
        source_page=entry.page if entry and entry.page is not None else (layout.source_page if layout else None),
        source_line=entry.label if entry and entry.label else (layout.source_line if layout else None),
        unit_source_text=layout.unit_source_text if layout else None,
        confidence="LOW",
        status=status,
        raw_label=layout.raw_label if layout else (entry.label if entry else None),
        source_bbox=layout.source_bbox if layout else (entry.bbox if entry else None),
        extraction_method="COMPILER_QUERY",
        semantic_model="compiler",
        semantic_confidence=0.0,
        entity_confidence=layout.entity_confidence if layout else 0.0,
        period_confidence=layout.period_confidence if layout else 0.0,
        unit_confidence=layout.unit_confidence if layout else 0.0,
        column_confidence=layout.column_confidence if layout else 0.0,
        validation_confidence=0.0,
        overall_certainty=0.0,
        certainty_band="NONE",
        comparison_role=(
            entry.comparison_role if entry and entry.comparison_role else (layout.comparison_role if layout else "CURRENT")
        ),
        duration_months=(
            entry.duration_months
            if entry and entry.duration_months is not None
            else (layout.duration_months if layout else None)
        ),
        validation_status="NOT_VALIDATED",
        review_status="REVIEW",
        evidence_json=_evidence_blob(
            report=report,
            publication_path="statement_compiler",
            candidate_origin=_candidate_origin(entry) if entry else None,
            issue_code=None,
            detail=issue or queried.issue,
            prior=layout.evidence_json if layout else None,
            entry=entry,
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
        review_status=layout.review_status,
        evidence_json=_evidence_blob(
            report=report,
            publication_path="explicit_layout_fallback",
            candidate_origin="layout_geometry",
            issue_code=issue_code,
            detail=detail,
            prior=layout.evidence_json,
        ),
    )
