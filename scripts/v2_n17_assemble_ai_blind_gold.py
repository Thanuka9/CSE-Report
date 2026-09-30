"""Validate and assemble N17 AI blind gold from partial JSONL shards.

Isolation: this script only validates schema/counts/SHA — it does not open
engine outputs. Partials must already be PDF-blind adjudicated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = {
    "PAT",
    "PBT",
    "OPERATING_PROFIT",
    "TOP_LINE",
    "EPS_BASIC",
    "EPS_DILUTED",
}
STOCK = {"NAVPS", "TOTAL_EQUITY", "TOTAL_ASSETS", "TOTAL_LIABILITIES"}
METRICS = tuple(sorted(FLOW | STOCK))
REVIEWER = "chatgpt-blind-source-review-2026-09-19"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def validate_row(row: dict, *, pdf_sha_by_id: dict[str, str]) -> list[str]:
    errors: list[str] = []
    fid = row.get("filing_version_id")
    metric = row.get("metric_code")
    presence = row.get("source_presence")
    if presence not in {"REPORTED", "NOT_REPORTED", "AMBIGUOUS"}:
        errors.append(f"{fid}/{metric}: bad source_presence={presence}")
    if row.get("split") != "HOLDOUT":
        errors.append(f"{fid}/{metric}: split must be HOLDOUT")
    if row.get("reviewer_1") != REVIEWER:
        errors.append(f"{fid}/{metric}: reviewer_1 must be {REVIEWER}")
    if row.get("adjudication_status") not in {
        "AI_REVIEWER_1_COMPLETE",
        "BLIND_SOURCE_REVIEW_COMPLETE",
    }:
        errors.append(f"{fid}/{metric}: bad adjudication_status")
    expected_sha = pdf_sha_by_id.get(str(fid))
    if expected_sha and row.get("pdf_sha256") != expected_sha:
        errors.append(f"{fid}/{metric}: pdf_sha256 mismatch")
    if presence == "REPORTED":
        for key in (
            "raw_source_label",
            "raw_source_value",
            "normalized_value",
            "entity_scope",
            "period_end",
            "comparison_role",
            "currency",
            "scale",
            "unit_dimension",
            "page",
            "evidence_text",
            "evidence_level",
        ):
            if row.get(key) in (None, ""):
                errors.append(f"{fid}/{metric}: REPORTED missing {key}")
        if metric in FLOW:
            if row.get("duration_months") != 3:
                errors.append(f"{fid}/{metric}: FLOW duration_months must be 3")
        if metric in STOCK:
            if row.get("duration_months") is not None:
                errors.append(f"{fid}/{metric}: STOCK duration_months must be null")
        if row.get("period_end") != "2025-12-31":
            errors.append(f"{fid}/{metric}: period_end must be 2025-12-31")
        if row.get("comparison_role") != "CURRENT":
            errors.append(f"{fid}/{metric}: comparison_role must be CURRENT")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partial-dir",
        type=Path,
        default=Path("outputs/n17_blind_partial"),
    )
    parser.add_argument(
        "--out-jsonl",
        type=Path,
        default=Path("tests/v2/source_truth/n17_ai_blind_gold.jsonl"),
    )
    parser.add_argument(
        "--out-manifest",
        type=Path,
        default=Path("tests/v2/source_truth/n17_ai_blind_gold_manifest.json"),
    )
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()

    identity = json.loads(
        (ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    items = identity["items"]
    pdf_sha_by_id = {it["filing_version_id"]: it["pdf_sha256"] for it in items}
    expected_keys = {
        (it["filing_version_id"], metric) for it in items for metric in METRICS
    }

    rows: list[dict] = []
    for path in sorted(args.partial_dir.glob("*.jsonl")):
        rows.extend(_load_jsonl(path))

    by_key: dict[tuple[str, str], dict] = {}
    dupes = 0
    for row in rows:
        key = (str(row.get("filing_version_id")), str(row.get("metric_code")))
        if key in by_key:
            dupes += 1
        by_key[key] = row

    # Intentional last-wins overwrites (zzz_* OCR clears) are informational only.
    errors: list[str] = []
    missing = sorted(expected_keys - set(by_key))
    extra = sorted(set(by_key) - expected_keys)
    if missing and not args.allow_incomplete:
        errors.append(f"missing slots: {len(missing)}")
    if extra:
        errors.append(f"extra slots: {len(extra)}")

    for key, row in sorted(by_key.items()):
        errors.extend(validate_row(row, pdf_sha_by_id=pdf_sha_by_id))

    ordered = [by_key[k] for k in sorted(by_key) if k in expected_keys]
    presence = Counter(str(r.get("source_presence")) for r in ordered)
    for key in ("REPORTED", "NOT_REPORTED", "AMBIGUOUS"):
        presence.setdefault(key, 0)

    contract = ROOT / "docs/v2/SOURCE_METRIC_TRUTH_CONTRACT.md"
    contract_sha = _sha256_file(contract) if contract.is_file() else None
    pdf_shas = {
        it["filing_version_id"]: {
            "pdf_sha256": it["pdf_sha256"],
            "local_file": it["local_file"],
            "verified_match": _sha256_file(ROOT / it["local_file"]) == it["pdf_sha256"]
            if (ROOT / it["local_file"]).is_file()
            else False,
        }
        for it in items
    }

    manifest = {
        "id": "n17-ai-blind-gold",
        "recovery_step": "N17",
        "status": "DRAFT_UNVALIDATED" if errors else "AI_BLIND_GOLD_READY_TO_LOCK",
        "gold_locked": False,
        "reviewer_1": REVIEWER,
        "adjudication_status": "AI_REVIEWER_1_COMPLETE",
        "method": "AI_BLIND_SOURCE_PDF_REVIEW",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_contract": "docs/v2/SOURCE_METRIC_TRUTH_CONTRACT.md",
        "source_contract_sha256": contract_sha,
        "plan": "docs/v2/N17_AI_BLIND_ADJUDICATION_AND_FINAL_EXECUTION_PLAN.md",
        "row_count": len(ordered),
        "expected_row_count": 130,
        "presence_counts": dict(presence),
        "pdf_sha256": pdf_shas,
        "duplicate_keys_overwritten": dupes,
        "validation_errors": errors[:50],
        "validation_error_count": len(errors),
        "missing_slots": [{"filing_version_id": a, "metric_code": b} for a, b in missing[:40]],
        "isolation_statement": (
            "V1/V2 outputs, CandidateTrace, SourceFacts, workbook, and selector "
            "outputs were not consulted for adjudication of these 13 holdout PDFs."
        ),
        "hard_rules": [
            "Do not run N18 until gold is committed and frozen",
            "Do not promote V2 / lower 8924",
            "Do not invent Q4 / TOTAL_LIABILITIES / GROUP→COMPANY",
        ],
    }

    args.out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.out_jsonl.open("w", encoding="utf-8") as fh:
        for row in ordered:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    args.out_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote_jsonl": str(args.out_jsonl),
                "wrote_manifest": str(args.out_manifest),
                "row_count": len(ordered),
                "presence_counts": dict(presence),
                "validation_error_count": len(errors),
                "errors_head": errors[:12],
            },
            indent=2,
        )
    )
    return 1 if errors and not args.allow_incomplete else 0


if __name__ == "__main__":
    raise SystemExit(main())
