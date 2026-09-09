"""Prepare and validate a human adjudication packet for the 100-issuer benchmark.

This module never manufactures MANUAL_QA truth.  It exports machine output and
source provenance with empty human fields, then validates completed adjudication
packets so a reviewer can build an independent benchmark without contaminating it
with pipeline-seeded answers.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from cse_financial_etl.config import infer_issuer_type

CORE_METRICS = (
    "PAT",
    "PBT",
    "EPS_SELECTED",
    "NAVPS",
    "OPERATING_PROFIT",
    "TOTAL_EQUITY",
    "TOTAL_ASSETS",
    "TOTAL_LIABILITIES",
    "TOP_LINE",
)
HUMAN_FIELDS = (
    "human_value",
    "human_entity_scope",
    "human_duration_months",
    "human_comparison_role",
    "human_unit",
    "human_scale_factor",
    "human_source_page",
    "human_verdict",
    "reviewer_id",
    "reviewed_at",
    "review_note",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _round_robin_issuers(rows: list[dict[str, str]], target: int) -> list[str]:
    by_type: dict[str, list[str]] = defaultdict(list)
    for issuer in sorted({row.get("issuer_name", "") for row in rows if row.get("issuer_name")}):
        by_type[infer_issuer_type(issuer)].append(issuer)
    buckets = {kind: list(values) for kind, values in sorted(by_type.items())}
    selected: list[str] = []
    while len(selected) < target and any(buckets.values()):
        progressed = False
        for kind in sorted(buckets):
            if not buckets[kind] or len(selected) >= target:
                continue
            selected.append(buckets[kind].pop(0))
            progressed = True
        if not progressed:
            break
    return selected


def prepare_adjudication_packet(
    project_root: Path,
    as_of_date: date,
    *,
    target_issuers: int = 100,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Create a deterministic, issuer-stratified human-review packet from a universe run."""

    facts_path = project_root / "outputs" / f"normalized_facts_{as_of_date.isoformat()}.csv"
    if not facts_path.exists():
        raise FileNotFoundError(f"Universe output not found: {facts_path}")
    rows = _read_csv(facts_path)
    rows = [row for row in rows if row.get("metric_code") in CORE_METRICS]
    selected_issuers = _round_robin_issuers(rows, target_issuers)
    if len(selected_issuers) < target_issuers:
        raise ValueError(
            f"Only {len(selected_issuers)} unique issuers are available; {target_issuers} required"
        )
    selected = set(selected_issuers)

    # One latest filing period per issuer, all core metrics from that filing.  This
    # keeps issuer breadth independent and avoids weighting one issuer by many quarters.
    latest_period: dict[str, str] = {}
    for row in rows:
        issuer = row.get("issuer_name", "")
        period = row.get("period_end", "")
        if issuer in selected and period > latest_period.get(issuer, ""):
            latest_period[issuer] = period

    packet_rows: list[dict[str, Any]] = []
    for row in rows:
        issuer = row.get("issuer_name", "")
        if issuer not in selected or row.get("period_end") != latest_period.get(issuer):
            continue
        machine = {
            "issuer_name": issuer,
            "issuer_type": infer_issuer_type(issuer),
            "symbol": row.get("symbol"),
            "period_end": row.get("period_end"),
            "metric_code": row.get("metric_code"),
            "machine_value": row.get("normalized_value"),
            "machine_status": row.get("status"),
            "machine_entity_scope": row.get("entity_scope"),
            "machine_duration_months": row.get("duration_months"),
            "machine_comparison_role": row.get("comparison_role"),
            "machine_unit": row.get("currency"),
            "machine_scale_factor": row.get("scale_factor"),
            "machine_source_page": row.get("source_page"),
            "machine_certainty": row.get("overall_certainty"),
            "filing_sha256": row.get("filing_sha256"),
            "source_url": row.get("source_url"),
            "local_path": row.get("local_path"),
        }
        machine.update({field: "" for field in HUMAN_FIELDS})
        packet_rows.append(machine)

    packet_rows.sort(key=lambda row: (selected_issuers.index(str(row["issuer_name"])), str(row["metric_code"])))
    destination = output_path or project_root / "outputs" / f"adjudication_packet_{as_of_date.isoformat()}.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = list(packet_rows[0]) if packet_rows else []
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(packet_rows)

    manifest = {
        "as_of_date": as_of_date.isoformat(),
        "target_issuers": target_issuers,
        "issuer_count": len(selected_issuers),
        "row_count": len(packet_rows),
        "issuer_type_counts": {
            kind: sum(infer_issuer_type(issuer) == kind for issuer in selected_issuers)
            for kind in sorted({infer_issuer_type(issuer) for issuer in selected_issuers})
        },
        "packet": str(destination),
        "truth_status": "UNADJUDICATED",
        "warning": "Machine values are context only and are not MANUAL_QA truth until independently reviewed.",
    }
    manifest_path = destination.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def validate_adjudication_packet(path: Path, *, target_issuers: int = 100) -> dict[str, Any]:
    """Validate completeness and independence fields without importing/fabricating truth."""

    rows = _read_csv(path)
    completed = [
        row
        for row in rows
        if row.get("human_verdict") in {"PASS", "FAIL"}
        and row.get("reviewer_id")
        and row.get("reviewed_at")
    ]
    issuers = {row.get("issuer_name", "") for row in completed if row.get("issuer_name")}
    incomplete_context = [
        row
        for row in completed
        if row.get("human_value") in (None, "")
        or row.get("human_entity_scope") in (None, "")
        or row.get("human_comparison_role") in (None, "")
        or row.get("human_unit") in (None, "")
    ]
    status = "READY_FOR_MANUAL_QA_IMPORT" if len(issuers) >= target_issuers and not incomplete_context else "INCOMPLETE"
    return {
        "status": status,
        "completed_rows": len(completed),
        "completed_issuer_count": len(issuers),
        "target_issuers": target_issuers,
        "incomplete_context_rows": len(incomplete_context),
        "independence_rule": "Only explicit human_* fields count; machine_* fields never certify themselves.",
    }
