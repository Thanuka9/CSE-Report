"""Separate redesign accuracy / coverage trackers (§48) — never one collapsed %."""

from __future__ import annotations

from collections import Counter
from typing import Any


def empty_redesign_metrics() -> dict[str, Counter[str]]:
    keys = (
        "document_reconstruction",
        "statement_classification",
        "header_column_ownership",
        "entity",
        "duration",
        "current_comparative",
        "unit",
        "semantic_row_label",
        "numeric_exact",
        "wrong_populated_cell",
        "core_metric_coverage",
        "recovery_success",
        "tunnel_agreement",
        "terminal_unresolved",
    )
    return {key: Counter() for key in keys}


def record_extraction_report(metrics: dict[str, Counter[str]], report: dict[str, Any]) -> None:
    quality = report.get("document_quality") or {}
    if quality.get("token_count"):
        metrics["document_reconstruction"]["PASS"] += 1
    else:
        metrics["document_reconstruction"]["FAIL"] += 1

    statements = report.get("statements_detected") or []
    if statements:
        metrics["statement_classification"]["PASS"] += 1
    else:
        metrics["statement_classification"]["UNTESTED"] += 1

    tunnel_a = report.get("tunnel_a") or {}
    tunnel_b = report.get("tunnel_b") or {}
    if tunnel_b and not tunnel_b.get("deferred") and not tunnel_b.get("error"):
        metrics["tunnel_agreement"]["OBSERVED"] += 1
    elif tunnel_a:
        metrics["tunnel_agreement"]["A_ONLY"] += 1

    for fact in report.get("final_facts") or []:
        status = str(fact.get("status") or "")
        if status == "EXTRACTED":
            metrics["core_metric_coverage"]["EXTRACTED"] += 1
            metrics["numeric_exact"]["CANDIDATE"] += 1
        elif status in {"CUMULATIVE_ONLY", "EXACT_QUARTER_NOT_REPORTED"}:
            metrics["duration"]["TERMINAL"] += 1
            metrics["terminal_unresolved"][status] += 1
        elif "GROUP" in status or status == "VALUE_CONTEXT_UNRESOLVED":
            metrics["entity"]["TERMINAL"] += 1
            metrics["terminal_unresolved"][status] += 1
        else:
            metrics["terminal_unresolved"][status or "UNKNOWN"] += 1

    for ticket in report.get("failure_tickets") or []:
        terminal = str(ticket.get("terminal") or "")
        if terminal == "RECOVERED":
            metrics["recovery_success"]["RECOVERED"] += 1
        else:
            metrics["recovery_success"]["NOT_RECOVERED"] += 1


def summarize_redesign_metrics(metrics: dict[str, Counter[str]]) -> dict[str, Any]:
    return {name: dict(counter) for name, counter in metrics.items()}
