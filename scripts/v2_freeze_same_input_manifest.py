"""Freeze same-input PDF SHA manifest for V1/V2 recovery comparison."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERIODS = ("2025-12-31", "2026-03-31", "2026-06-30")
RUN_ID = "same_input_2026-09-09"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_pdf_name(path: Path) -> dict[str, str] | None:
    # 2025-12-31_50214_84736b4e3d80f26b.pdf
    m = re.match(r"^(?P<period>\d{4}-\d{2}-\d{2})_(?P<filing_id>\d+)_(?P<sha16>[0-9a-f]{16})$", path.stem)
    if not m:
        return None
    return {
        "period_end": m.group("period"),
        "filing_id": m.group("filing_id"),
        "sha16": m.group("sha16"),
        "issuer_dir": path.parent.name,
        "local_path": str(path.relative_to(ROOT)).replace("\\", "/"),
    }


def main() -> int:
    filings_root = ROOT / "data" / "raw" / "filings"
    items: list[dict] = []
    for pdf in sorted(filings_root.rglob("*.pdf")):
        meta = _parse_pdf_name(pdf)
        if meta is None or meta["period_end"] not in PERIODS:
            continue
        full_sha = _sha256_file(pdf)
        if not full_sha.startswith(meta["sha16"]):
            # keep but flag mismatch
            meta["sha16_mismatch"] = True
        items.append(
            {
                **meta,
                "pdf_sha256": full_sha,
                "bytes": pdf.stat().st_size,
            }
        )

    # Prefer one filing per (issuer_dir, period_end): lowest filing_id (stable)
    chosen: dict[tuple[str, str], dict] = {}
    for item in items:
        key = (item["issuer_dir"], item["period_end"])
        prev = chosen.get(key)
        if prev is None or int(item["filing_id"]) < int(prev["filing_id"]):
            chosen[key] = item
    selected = sorted(chosen.values(), key=lambda r: (r["issuer_dir"], r["period_end"]))

    out_dir = ROOT / "reports" / "v1_v2_same_input" / RUN_ID
    out_dir.mkdir(parents=True, exist_ok=True)

    # Dirty-SHA inconsistency note from E13 clean folder
    e13_summary = ROOT / "tests/v2/universe/e13_v2_challenger_clean_d29b392/e13_summary.json"
    e13_manifest = ROOT / "tests/v2/universe/e13_v2_challenger_clean_d29b392/run_manifest_2026-09-09.json"
    dirty_note = {
        "issue": "E13 folder labeled clean_d29b392 but run_manifest working_tree_dirty=true",
        "e13_summary_git_commit_sha": None,
        "e13_manifest_git_commit_sha": None,
        "e13_manifest_working_tree_dirty": None,
        "e13_manifest_git_describe": None,
        "resolution": (
            "Treat d29b392 as the intended code pin; do not claim the prior E13 run "
            "reproducible until a fresh clean-tree rerun rewrites the manifest. "
            "This freeze uses on-disk PDF bytes + computed SHA256, independent of that run."
        ),
    }
    if e13_summary.is_file():
        s = json.loads(e13_summary.read_text(encoding="utf-8"))
        dirty_note["e13_summary_git_commit_sha"] = s.get("git_commit_sha")
    if e13_manifest.is_file():
        m = json.loads(e13_manifest.read_text(encoding="utf-8"))
        dirty_note["e13_manifest_git_commit_sha"] = m.get("git_commit_sha")
        dirty_note["e13_manifest_working_tree_dirty"] = m.get("working_tree_dirty")
        dirty_note["e13_manifest_git_describe"] = m.get("git_describe")

    manifest = {
        "id": "v1-v2-same-input-freeze",
        "run_id": RUN_ID,
        "status": "FROZEN_INPUTS",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "periods": list(PERIODS),
        "selection_rule": (
            "One PDF per (issuer_directory, period_end) among local data/raw/filings "
            "for target periods; choose lowest CSE filing_id when multiples exist. "
            "This is a governed comparator freeze of available bytes — not a claim "
            "that it equals the historic production 829 selection unless counts match."
        ),
        "filings_discovered_in_periods": len(items),
        "filings_selected": len(selected),
        "historic_e13_selected_filing_count": 829,
        "selection_count_matches_e13_829": len(selected) == 829,
        "dirty_sha_inconsistency": dirty_note,
        "filings": selected,
    }
    (out_dir / "input_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "gap_summary.json").write_text(
        json.dumps(
            {
                "id": "v1-v2-gap-summary",
                "run_id": RUN_ID,
                "status": "SCAFFOLD",
                "note": (
                    "Categories BOTH_SAME / V1_ONLY_SOURCE_VALID / etc. require a "
                    "same-input V1 vs V2 fact ledger run — not yet measured."
                ),
                "counts": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out_dir / 'input_manifest.json'} selected={len(selected)} discovered={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
