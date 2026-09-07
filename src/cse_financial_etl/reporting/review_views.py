"""Review and Accuracy_Quality view builders (§54) — offline / file-based.

Authenticated human approval workflow is external. This module produces the
machine-readable review packets and Accuracy_Quality payload from a finalized
manifest so workbook / dashboard / exports stay consistent.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from cse_financial_etl.storage.stage_cache import atomic_write_text


def build_review_packet(
    *,
    fact: dict[str, Any],
    competing_candidates: list[dict[str, Any]] | None = None,
    recovery_attempts: list[dict[str, Any]] | None = None,
    blocked_reason: str | None = None,
    source_page: int | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Complete review packet — value crop alone is insufficient (§54)."""

    return {
        "fact": fact,
        "source_page": source_page or fact.get("source_page"),
        "label": fact.get("raw_label") or fact.get("source_line"),
        "scope_period_unit": {
            "entity_scope": fact.get("entity_scope"),
            "duration_months": fact.get("duration_months"),
            "comparison_role": fact.get("comparison_role"),
            "currency": fact.get("currency"),
            "scale_factor": fact.get("scale_factor"),
            "unit_source_text": fact.get("unit_source_text"),
        },
        "competing_candidates": competing_candidates or [],
        "failed_dimensions": _failed_dimensions(fact, blocked_reason),
        "recovery_attempts": recovery_attempts or [],
        "publication_blocked_reason": blocked_reason,
        "evidence": evidence or {},
        "approval_binding": {
            "requires_authenticated_reviewer": True,
            "source_version": evidence.get("compiler_report_summary", {}).get("filing_sha")
            if evidence
            else None,
            "policy_version": "redesign_r2",
            "note": "Reviewer identity must come from the approved operating workflow, not an editable CSV name.",
        },
    }


def build_accuracy_quality_view(
    *,
    universe_filings: int,
    filings_processed: int,
    published_facts: int,
    eligible_disclosures: int | None,
    independent_review_coverage: float | None,
    measured_precision: float | None,
    false_absence_rate: float | None,
    unresolved_issues: int,
    release_status: str,
    numerators: dict[str, int] | None = None,
    denominators: dict[str, int] | None = None,
    benchmark_provenance: str | None = None,
    evidence_confidence_separate: bool = True,
) -> dict[str, Any]:
    """Accuracy_Quality workbook / dashboard payload (§54)."""

    return {
        "universe_filing_coverage": {
            "numerator": filings_processed,
            "denominator": universe_filings,
            "rate": (filings_processed / universe_filings) if universe_filings else None,
        },
        "numeric_coverage": {
            "published_facts": published_facts,
            "eligible_disclosures": eligible_disclosures,
            "rate": (
                published_facts / eligible_disclosures
                if eligible_disclosures
                else None
            ),
        },
        "independent_review_coverage": independent_review_coverage,
        "eligible_disclosure_recall": (
            published_facts / eligible_disclosures if eligible_disclosures else None
        ),
        "measured_publication_precision": measured_precision,
        "false_absence_rate": false_absence_rate,
        "unresolved_issues": unresolved_issues,
        "release_status": release_status,
        "numerators": numerators or {},
        "denominators": denominators or {},
        "benchmark_sample_provenance": benchmark_provenance,
        "evidence_confidence_separate_from_accuracy": evidence_confidence_separate,
        "external_remainder": (
            "100-issuer independent human adjudication and authenticated reviewer "
            "identity binding remain operating-process deliverables."
        ),
    }


def write_review_bundle(
    output_dir: Path,
    *,
    packets: list[dict[str, Any]],
    accuracy_quality: dict[str, Any],
    manifest_id: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_counts = Counter(
        str(p.get("fact", {}).get("status") or "UNKNOWN") for p in packets
    )
    bundle = {
        "manifest_id": manifest_id,
        "packet_count": len(packets),
        "status_counts": dict(status_counts),
        "accuracy_quality": accuracy_quality,
        "packets": packets,
    }
    path = output_dir / f"review_bundle_{manifest_id}.json"
    atomic_write_text(path, json.dumps(bundle, indent=2, default=str))
    return path


def _failed_dimensions(fact: dict[str, Any], blocked_reason: str | None) -> list[str]:
    failed: list[str] = []
    status = str(fact.get("status") or "")
    if "ENTITY" in status or "GROUP" in status or "CONSOLIDATED" in status:
        failed.append("entity")
    if "QUARTER" in status or "CUMULATIVE" in status or "DURATION" in status:
        failed.append("duration")
    if "UNIT" in status:
        failed.append("unit")
    if "CONTEXT" in status or "COLUMN" in status:
        failed.append("column_context")
    if blocked_reason:
        failed.append(blocked_reason)
    return failed
