"""Build a frozen V1 fact snapshot and shadow-diff it against V2."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from cse_financial_etl.v2.diagnostics.real_filings import project_root, resolve_filing_pdf
from cse_financial_etl.v2.diagnostics.serialization import source_fact_to_mapping
from cse_financial_etl.v2.diagnostics.shadow import shadow_diff
from cse_financial_etl.v2.orchestration.filing_pipeline import run_pdf_pipeline

SOURCE_STATUSES = {"EXTRACTED", "EXTRACTED_DERIVED"}
PIN_RELATIVE = Path("tests/v2/golden/universe_pin.json")
FALLBACK_SNAPSHOT = Path("outputs") / "normalized_facts_2026-09-05.csv"


def v1_rows_from_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def v1_row_to_mapping(row: dict[str, str]) -> dict[str, object]:
    duration_raw = row.get("duration_months")
    duration: int | None = None
    if isinstance(duration_raw, str) and duration_raw.strip() != "":
        duration = int(duration_raw)
    return {
        "filing_version_id": row.get("filing_sha256") or row.get("filing_id") or "",
        "issuer_id": row.get("symbol") or "",
        "entity_scope": row.get("entity_scope") or "",
        "period_end": row.get("period_end") or "",
        "duration_months": duration,
        "comparison_role": row.get("comparison_role") or "CURRENT",
        "metric_code": row.get("metric_code") or "",
        "normalized_value": str(row.get("normalized_value") or ""),
        "validation_status": row.get("validation_status") or "",
        "review_status": row.get("review_status") or "",
        "publication_status": "ELIGIBLE" if row.get("status") in SOURCE_STATUSES else "WITHHELD",
        "parser_path": row.get("extraction_method") or "v1",
        "reason_codes": row.get("missing_reason") or "",
        "local_path": row.get("local_path") or "",
    }


def load_v1_universe_mappings(path: Path) -> tuple[dict[str, object], ...]:
    return tuple(
        v1_row_to_mapping(row)
        for row in v1_rows_from_csv(path)
        if row.get("status") in SOURCE_STATUSES and row.get("normalized_value")
    )


def shadow_v1_csv_against_v2(
    csv_path: Path,
    pdf_by_name: dict[str, Path],
    *,
    limit: int = 6,
) -> dict[str, object]:
    reference_all = [
        item
        for item in load_v1_universe_mappings(csv_path)
        if Path(str(item.get("local_path") or "")).name in pdf_by_name
    ]
    current: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in reference_all:
        name = Path(str(item.get("local_path") or "")).name
        pdf = pdf_by_name.get(name)
        if pdf is None or name in seen:
            continue
        if len(seen) >= limit:
            break
        seen.add(name)
        _statements, facts, _derived, _metrics = run_pdf_pipeline(
            pdf,
            issuer_id=str(item.get("issuer_id") or pdf.stem),
            filing_version_id=str(item.get("filing_version_id") or pdf.stem),
        )
        current.extend(source_fact_to_mapping(fact) for fact in facts)
    reference = tuple(
        item for item in reference_all if Path(str(item.get("local_path") or "")).name in seen
    )
    return shadow_diff(reference, tuple(current))


def overlapping_pdfs_from_snapshot(csv_path: Path, *, limit: int = 6) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for row in v1_rows_from_csv(csv_path):
        local = Path(row.get("local_path") or "")
        if not local.name or local.name in found:
            continue
        resolved = resolve_filing_pdf(str(local)) or (local if local.is_file() else None)
        if resolved is None:
            continue
        found[local.name] = resolved
        if len(found) >= limit:
            break
    return found


def load_universe_pin(*, root: Path | None = None) -> dict[str, object]:
    root = root or project_root()
    payload = json.loads((root / PIN_RELATIVE).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("universe pin must be a JSON object")
    return {str(key): value for key, value in payload.items()}


def default_v1_snapshot() -> Path | None:
    root = project_root()
    pin = load_universe_pin(root=root)
    if bool(pin.get("not_frozen_september_10")) is False:
        raise ValueError("universe pin must not claim a frozen September-10 snapshot")
    relative = str(pin.get("relative_path") or FALLBACK_SNAPSHOT.as_posix())
    path = root / relative
    if path.is_file():
        return path
    fallback = root / FALLBACK_SNAPSHOT
    return fallback if fallback.is_file() else None
