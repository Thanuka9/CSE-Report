"""End-to-end Revision 2 extraction compiler orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.accounting.sector_profiles import profile_for_issuer
from cse_financial_etl.compiler.known_context import build_known_context
from cse_financial_etl.config import infer_entity_scope
from cse_financial_etl.facts.derived_facts import compute_quarter_ratios
from cse_financial_etl.facts.query_engine import query_target_facts
from cse_financial_etl.recovery.failure_diagnoser import diagnose_failures
from cse_financial_etl.recovery.recovery_router import run_recovery
from cse_financial_etl.resolution.arbiter import arbitrate_candidates
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger
from cse_financial_etl.resolution.global_resolver import global_resolve
from cse_financial_etl.resolution.uncertainty import uncertainty_from_entry
from cse_financial_etl.tunnels.tunnel_a_geometry import run_tunnel_a
from cse_financial_etl.tunnels.tunnel_b_table import run_tunnel_b
from cse_financial_etl.validation.final_validator import (
    build_extraction_report,
    gate_no_overpublication,
    validate_source_fact,
)


def compile_filing(
    pdf_path: Path,
    *,
    issuer_name: str,
    symbol: str,
    period_end: date,
    ocr_enabled: bool = True,
    ocr_dir: Path | None = None,
    legacy_facts: list[Any] | None = None,
    run_tunnel_b_always: bool = False,
    diagnostics_dir: Path | None = None,
) -> dict[str, Any]:
    """Run A (+B as needed), Resolver C, arbiter, recovery, target queries, final checks."""

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
    tunnel_a = run_tunnel_a(
        pdf_path,
        issuer_name=issuer_name,
        symbol=symbol,
        period_end=period_end,
        ocr_enabled=ocr_enabled,
        ocr_dir=ocr_dir,
        known=known,
        legacy_facts=legacy_facts,
    )
    ledger: CandidateLedger = tunnel_a["ledger"]
    unresolved_before_b = [
        e for e in ledger.entries if e.status == "unresolved" and e.normalized_value is None
    ]
    tunnel_b_report = None
    # Full Tunnel B only when running pure compiler mode (no layout seed) or forced.
    if run_tunnel_b_always or legacy_facts is None:
        try:
            tunnel_b = run_tunnel_b(pdf_path, known=known, period_end=period_end)
            tunnel_b_report = tunnel_b["report"]
            for entry in tunnel_b["ledger"].entries:
                ledger.add(entry)
        except Exception as exc:  # pragma: no cover - defensive
            tunnel_b_report = {"error": str(exc)}
    elif unresolved_before_b:
        tunnel_b_report = {
            "deferred": True,
            "reason": "unresolved_after_layout_seed",
            "unresolved_concepts": sorted({e.concept for e in unresolved_before_b}),
        }

    decisions = arbitrate_candidates(
        ledger,
        required_entity=entity,
        target_duration=3,
        target_period_end=period_end.isoformat(),
    )
    ledger, resolver, equation_results = global_resolve(
        ledger,
        required_entity=entity,
        target_duration=3,
    )
    # Targeted recovery for still-unresolved concepts.
    unresolved_map: dict[str, list[str]] = {}
    for entry in ledger.unresolved():
        unresolved_map.setdefault(entry.concept, []).extend(entry.reasons or ["unresolved"])
    for decision in decisions:
        if decision.status != "SELECTED":
            unresolved_map.setdefault(decision.concept, []).append(decision.reason)
    tickets = diagnose_failures(unresolved_map)
    unit_texts = []
    for statement in tunnel_a.get("statements") or []:
        for item in getattr(statement, "unit_evidence", []) or []:
            if item.get("text"):
                unit_texts.append(item["text"])
    tickets = run_recovery(
        tickets,
        ledger,
        context={
            "required_entity": entity,
            "target_duration": 3,
            "pdf_path": str(pdf_path),
            "unit_texts": unit_texts,
            "row_labels": [
                e.label for e in ledger.entries if e.label
            ][:200],
        },
    )
    # Re-arbitrate after recovery.
    decisions = arbitrate_candidates(
        ledger,
        required_entity=entity,
        target_duration=3,
        target_period_end=period_end.isoformat(),
    )
    queried = query_target_facts(ledger, entity=entity, period_end=period_end)
    values = {
        fact.metric_code: (fact.entry.normalized_value if fact.entry else None) for fact in queried
    }
    ratios = compute_quarter_ratios(
        pat=values.get("PAT"),
        equity=values.get("TOTAL_EQUITY"),
        assets=values.get("TOTAL_ASSETS"),
        liabilities=values.get("TOTAL_LIABILITIES"),
        top_line=values.get("TOP_LINE"),
    )
    final_checks = [
        validate_source_fact(fact.entry, required_entity=entity, target_duration=3)
        for fact in queried
        if fact.entry is not None
    ]
    violations = gate_no_overpublication(queried, ratios)
    uncertainty = [
        uncertainty_from_entry(
            entry.concept,
            entry_status=entry.status,
            reasons=entry.reasons,
        ).as_dict()
        for entry in ledger.unresolved()
    ]
    report = build_extraction_report(
        filing_sha=tunnel_a["document"].source_sha256,
        known={
            "issuer": issuer_name,
            "symbol": symbol,
            "entity": entity,
            "period_end": period_end.isoformat(),
            "sector": profile.code,
        },
        document_quality=tunnel_a["document"].evidence_dict()["quality"],
        statements_detected=[
            {
                "type": s.statement_type,
                "pages": [s.page_start, s.page_end],
                "rows": len(s.rows),
            }
            for s in tunnel_a.get("statements") or []
        ],
        tunnel_a=tunnel_a["report"],
        tunnel_b=tunnel_b_report,
        resolver_c=resolver.report,
        arbiter=[
            {
                "concept": d.concept,
                "status": d.status,
                "reason": d.reason,
                "selected": d.selected.entry_id if d.selected else None,
            }
            for d in decisions
        ],
        failure_tickets=[
            {
                "id": t.ticket_id,
                "family": t.family,
                "terminal": t.terminal_status,
                "attempts": t.attempts,
            }
            for t in tickets
        ],
        recovery_attempts=[a for t in tickets for a in t.attempts],
        final_facts=[
            {
                "metric": f.metric_code,
                "status": f.status,
                "value": str(f.entry.normalized_value)
                if f.entry and f.entry.normalized_value is not None
                else None,
                "issue": f.issue,
            }
            for f in queried
        ]
        + [
            {
                "metric": r.code,
                "status": r.status,
                "value": str(r.value) if r.value is not None else None,
                "issue": r.issue,
            }
            for r in ratios
        ],
        terminal_unresolved=uncertainty,
    )
    report["equation_results"] = [
        {"id": r.equation_id, "status": r.status, "detail": r.detail} for r in equation_results
    ]
    report["no_overpublication_violations"] = violations
    report["final_checks"] = [asdict(c) for c in final_checks]

    if diagnostics_dir is not None:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        out = diagnostics_dir / f"{pdf_path.stem}.extraction_report.json"
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    return {
        "known": known,
        "ledger": ledger,
        "queried": queried,
        "ratios": ratios,
        "tickets": tickets,
        "decisions": decisions,
        "report": report,
        "legacy_facts": legacy_facts,
    }
