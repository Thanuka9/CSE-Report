"""Prepare and validate a stratified human adjudication packet for the 100-issuer benchmark.

This module never manufactures MANUAL_QA truth. It exports machine output and source
provenance with empty human fields, then validates completed packets. R4 selection is
deterministic across issuer type, reporting period and extraction difficulty so a strong
aggregate sample cannot hide one weak sector/layout family.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
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
PUBLISHABLE = {"EXTRACTED", "EXTRACTED_DERIVED"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _quarter_label(period_end: str) -> str:
    try:
        month = date.fromisoformat(period_end).month
    except ValueError:
        return "UNKNOWN"
    return {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, f"M{month:02d}")


def _difficulty_flags(rows: list[dict[str, str]]) -> tuple[str, ...]:
    flags: set[str] = set()
    if any("OCR" in str(row.get("extraction_method") or "").upper() for row in rows):
        flags.add("OCR")
    if any(str(row.get("status") or "") not in PUBLISHABLE for row in rows):
        flags.add("WITHHELD_OR_MISSING")
    if any(str(row.get("entity_scope") or "") not in {"COMPANY", "BANK"} for row in rows):
        flags.add("NONSTANDARD_SCOPE")
    if any(str(row.get("metric_code") or "") == "TOTAL_LIABILITIES" for row in rows):
        flags.add("BALANCE_SHEET")
    issuer_type = infer_issuer_type(str(rows[0].get("issuer_name") or "")) if rows else "OTHER"
    if issuer_type in {"BANK", "FINANCE_COMPANY", "INSURANCE"}:
        flags.add(f"SECTOR_{issuer_type}")
    return tuple(sorted(flags))


def _candidate_score(rows: list[dict[str, str]]) -> tuple[int, str, str]:
    flags = _difficulty_flags(rows)
    weights = {
        "OCR": 8,
        "WITHHELD_OR_MISSING": 5,
        "NONSTANDARD_SCOPE": 4,
        "SECTOR_INSURANCE": 4,
        "SECTOR_BANK": 3,
        "SECTOR_FINANCE_COMPANY": 3,
        "BALANCE_SHEET": 1,
    }
    score = sum(weights.get(flag, 0) for flag in flags)
    issuer = str(rows[0].get("issuer_name") or "") if rows else ""
    period = str(rows[0].get("period_end") or "") if rows else ""
    return (-score, issuer.casefold(), period)


def _stratified_issuer_periods(
    rows: list[dict[str, str]], target: int
) -> list[tuple[str, str]]:
    """Round-robin across issuer type × quarter, preferring difficult evidence."""

    by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        issuer = str(row.get("issuer_name") or "")
        period = str(row.get("period_end") or "")
        if issuer and period:
            by_pair[(issuer, period)].append(row)

    buckets: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    for pair in by_pair:
        issuer, period = pair
        key = (infer_issuer_type(issuer), _quarter_label(period))
        buckets[key].append(pair)
    for values in buckets.values():
        values.sort(key=lambda pair: _candidate_score(by_pair[pair]))

    selected: list[tuple[str, str]] = []
    used_issuers: set[str] = set()
    while len(selected) < target and any(buckets.values()):
        progressed = False
        for key in sorted(buckets):
            while buckets[key] and buckets[key][0][0] in used_issuers:
                buckets[key].pop(0)
            if not buckets[key] or len(selected) >= target:
                continue
            pair = buckets[key].pop(0)
            selected.append(pair)
            used_issuers.add(pair[0])
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
    """Create a deterministic, sector/period/difficulty-stratified review packet."""

    facts_path = project_root / "outputs" / f"normalized_facts_{as_of_date.isoformat()}.csv"
    if not facts_path.exists():
        raise FileNotFoundError(f"Universe output not found: {facts_path}")
    rows = _read_csv(facts_path)
    rows = [row for row in rows if row.get("metric_code") in CORE_METRICS]
    selected_pairs = _stratified_issuer_periods(rows, target_issuers)
    if len(selected_pairs) < target_issuers:
        raise ValueError(
            f"Only {len(selected_pairs)} unique issuers are available; {target_issuers} required"
        )
    selected = set(selected_pairs)
    pair_order = {pair: index for index, pair in enumerate(selected_pairs)}

    rows_by_pair: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        pair = (str(row.get("issuer_name") or ""), str(row.get("period_end") or ""))
        if pair in selected:
            rows_by_pair[pair].append(row)

    packet_rows: list[dict[str, Any]] = []
    for pair in selected_pairs:
        issuer, period = pair
        flags = ",".join(_difficulty_flags(rows_by_pair[pair]))
        for row in rows_by_pair[pair]:
            machine = {
                "issuer_name": issuer,
                "issuer_type": infer_issuer_type(issuer),
                "symbol": row.get("symbol"),
                "period_end": period,
                "fiscal_quarter": _quarter_label(period),
                "difficulty_flags": flags,
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
                "machine_extraction_method": row.get("extraction_method"),
                "filing_sha256": row.get("filing_sha256"),
                "source_url": row.get("source_url"),
                "local_path": row.get("local_path"),
            }
            machine.update({field: "" for field in HUMAN_FIELDS})
            packet_rows.append(machine)

    packet_rows.sort(
        key=lambda row: (
            pair_order[(str(row["issuer_name"]), str(row["period_end"]))],
            str(row["metric_code"]),
        )
    )
    destination = (
        output_path
        or project_root / "outputs" / f"adjudication_packet_{as_of_date.isoformat()}.csv"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    headers = list(packet_rows[0]) if packet_rows else []
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(packet_rows)

    selected_issuers = [issuer for issuer, _period in selected_pairs]
    manifest = {
        "as_of_date": as_of_date.isoformat(),
        "target_issuers": target_issuers,
        "issuer_count": len(selected_issuers),
        "row_count": len(packet_rows),
        "sampling_policy": "DETERMINISTIC_ISSUER_TYPE_X_QUARTER_X_DIFFICULTY_ROUND_ROBIN",
        "issuer_type_counts": dict(
            Counter(infer_issuer_type(issuer) for issuer in selected_issuers)
        ),
        "quarter_counts": dict(Counter(_quarter_label(period) for _issuer, period in selected_pairs)),
        "difficulty_flag_counts": dict(
            Counter(
                flag
                for pair in selected_pairs
                for flag in _difficulty_flags(rows_by_pair[pair])
            )
        ),
        "packet": str(destination),
        "truth_status": "UNADJUDICATED",
        "warning": (
            "Machine values are context only and are not MANUAL_QA truth until independently reviewed."
        ),
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
    status = (
        "READY_FOR_MANUAL_QA_IMPORT"
        if len(issuers) >= target_issuers and not incomplete_context
        else "INCOMPLETE"
    )
    return {
        "status": status,
        "completed_rows": len(completed),
        "completed_issuer_count": len(issuers),
        "target_issuers": target_issuers,
        "incomplete_context_rows": len(incomplete_context),
        "independence_rule": (
            "Only explicit human_* fields count; machine_* fields never certify themselves."
        ),
    }
