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
from cse_financial_etl.document.document_ir import CanonicalDocumentIR
from cse_financial_etl.facts.derived_facts import compute_quarter_ratios
from cse_financial_etl.facts.query_engine import query_target_facts
from cse_financial_etl.recovery.failure_diagnoser import diagnose_failures
from cse_financial_etl.recovery.recovery_router import run_recovery
from cse_financial_etl.resolution.arbiter import arbitrate_candidates
from cse_financial_etl.resolution.candidate_ledger import CandidateLedger
from cse_financial_etl.resolution.global_resolver import global_resolve
from cse_financial_etl.resolution.resource_budget import ResourceBudget
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
    document: CanonicalDocumentIR | None = None,
    compile_statements: bool = True,
    run_tunnel_b_always: bool = False,
    tunnel_b_sample_every: int = 8,
    diagnostics_dir: Path | None = None,
) -> dict[str, Any]:
    """Run A (+B as needed), Resolver C, arbiter, recovery, target queries, final checks.

    Tunnel B is invoked for unresolved / risky core concepts and for a deterministic
    sample (``1 / tunnel_b_sample_every`` by filing sha) of A successes so that the
    independent reader is continuously measured against A, not only on failures.
    """

    budget = ResourceBudget()
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
        document=document,
        compile_statements=compile_statements,
    )
    ledger: CandidateLedger = tunnel_a["ledger"]
    filing_sha = tunnel_a["document"].source_sha256

    # First arbitration on A alone decides whether B is needed.
    decisions = arbitrate_candidates(
        ledger,
        required_entity=entity,
        target_duration=3,
        target_period_end=period_end.isoformat(),
    )
    risky = _risky_concepts(ledger, decisions)
    core_missing = _core_concepts_missing(ledger)
    b_policy = tunnel_b_policy(
        filing_sha=filing_sha,
        risky_concepts=risky,
        core_missing=core_missing,
        force=run_tunnel_b_always,
        pdf_present=pdf_path.exists() and pdf_path.stat().st_size > 64,
        sample_every=tunnel_b_sample_every,
    )
    tunnel_b_report: dict[str, Any] = {"invoked": False, "policy": b_policy}
    if b_policy["invoke"]:
        if budget.exhausted():
            tunnel_b_report.update(
                {"deferred": True, "reason": budget.stop_reason or "BUDGET_EXHAUSTED"}
            )
        else:
            try:
                tunnel_b = run_tunnel_b(pdf_path, known=known, period_end=period_end)
                tunnel_b_report.update(tunnel_b["report"])
                tunnel_b_report["invoked"] = True
                for entry in tunnel_b["ledger"].entries:
                    ledger.add(entry)
            except Exception as exc:  # pragma: no cover - defensive
                tunnel_b_report.update({"error": str(exc)})
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
            "row_labels": [e.label for e in ledger.entries if e.label][:200],
        },
    )
    decisions = arbitrate_candidates(
        ledger,
        required_entity=entity,
        target_duration=3,
        target_period_end=period_end.isoformat(),
    )
    recovery_attempted = any(t.attempts for t in tickets)
    queried = query_target_facts(
        ledger,
        entity=entity,
        period_end=period_end,
        target_duration=3,
        recovery_attempted=recovery_attempted,
    )
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
        validate_source_fact(
            fact.entry,
            required_entity=entity,
            target_duration=3,
            target_period_end=period_end.isoformat(),
            concept=fact.concept,
        )
        for fact in queried
        if fact.entry is not None and fact.status == "EXTRACTED"
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
    report["core_concepts_missing_before_b"] = sorted(core_missing)
    report["risky_concepts_before_b"] = sorted(risky)
    report["native_compiler_success"] = bool(tunnel_a["report"].get("native_compiler_success"))
    report["compiled_statements"] = int(tunnel_a["report"].get("statements") or 0)
    report["arbiter_decisions"] = [
        {
            "concept": d.concept,
            "status": d.status,
            "reason": d.reason,
            "reasons": list(d.reasons),
            "selected": d.selected.entry_id if d.selected else None,
            "alternatives": list(d.alternatives),
        }
        for d in decisions
    ]
    report["resource_budget"] = budget.as_dict()
    if budget.exhausted():
        report["budget_stop_reason"] = budget.stop_reason

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
        "required_entity": entity,
    }


CORE_CONCEPTS = frozenset(
    {
        "PAT",
        "PBT",
        "TOP_LINE",
        "OPERATING_PROFIT",
        "TOTAL_ASSETS",
        "TOTAL_EQUITY",
        "TOTAL_LIABILITIES",
        "EPS_BASIC",
        "NAVPS",
    }
)


def _core_concepts_missing(ledger: CandidateLedger) -> set[str]:
    from cse_financial_etl.accounting.ontology import TARGET_CONCEPT_MAP

    present = {
        TARGET_CONCEPT_MAP.get(e.concept, e.concept)
        for e in ledger.entries
        if e.normalized_value is not None and e.status != "rejected"
    }
    return set(CORE_CONCEPTS) - present


def _risky_concepts(ledger: CandidateLedger, decisions: list[Any]) -> set[str]:
    """Core concepts A could not settle: no selection, abstention, or a selection that
    rests on a single low-score / layout-assist candidate."""

    from cse_financial_etl.accounting.ontology import TARGET_CONCEPT_MAP

    risky: set[str] = set()
    for decision in decisions:
        target = TARGET_CONCEPT_MAP.get(decision.concept, decision.concept)
        if target not in CORE_CONCEPTS:
            continue
        if decision.status != "SELECTED" or decision.selected is None:
            risky.add(target)
            continue
        selected = decision.selected
        if selected.evidence.get("candidate_origin") == "layout_geometry" or (
            float(selected.evidence.get("semantic_score", selected.score) or 0.0) < 0.9
            and not selected.evidence.get("corroborated_by")
        ):
            risky.add(target)
    return risky


def tunnel_b_policy(
    *,
    filing_sha: str,
    risky_concepts: set[str],
    core_missing: set[str],
    force: bool,
    pdf_present: bool,
    sample_every: int,
) -> dict[str, Any]:
    """Decide whether the independent reader runs, and record why."""

    sampled = False
    if filing_sha and sample_every > 0:
        try:
            sampled = int(filing_sha[-2:], 16) % sample_every == 0
        except ValueError:
            sampled = False
    reasons: list[str] = []
    if force:
        reasons.append("forced")
    if core_missing:
        reasons.append("core_missing")
    if risky_concepts:
        reasons.append("risky_concepts")
    if sampled:
        reasons.append("audit_sample")
    invoke = pdf_present and bool(reasons)
    return {
        "invoke": invoke,
        "reasons": reasons,
        "risky_concepts": sorted(risky_concepts),
        "core_missing": sorted(core_missing),
        "audit_sample": sampled,
        "pdf_present": pdf_present,
    }
