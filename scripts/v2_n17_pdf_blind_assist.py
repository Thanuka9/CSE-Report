"""V01 helper: PDF-only N17 blind fill progress (no V1/V2 peek).

Reads text layer from holdout PDFs and fills only high-confidence slots where
an exact source label + numeric are visible. Does not lock gold.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "tests/v2/source_truth/n17_blind_review_queue.json"
IDENTITY = ROOT / "tests/v2/source_truth/holdout_v2_identity_manifest.json"
PROGRESS = ROOT / "tests/v2/source_truth/n17_blind_adjudication_progress.json"

_NUM = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?")

# Conservative label cues only — human must still confirm before gold lock.
LABEL_CUES: dict[str, tuple[str, ...]] = {
    "TOP_LINE": ("revenue", "gross income", "interest income", "income"),
    "OPERATING_PROFIT": ("operating profit", "profit from operating", "operating income"),
    "PBT": ("profit before tax", "profit before taxation", "profit before income tax"),
    "PAT": ("profit for the period", "profit for the year", "net profit", "profit after tax"),
    "TOTAL_ASSETS": ("total assets",),
    "TOTAL_EQUITY": ("total equity", "total shareholders", "equity attributable"),
    "TOTAL_LIABILITIES": ("total liabilities",),
    "EPS_BASIC": ("basic", "earnings per share"),
    "EPS_DILUTED": ("diluted",),
    "NAVPS": ("net asset", "net assets per share", "navps"),
}


def _pdf_text(path: Path) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def _find_candidates(text: str, metric: str) -> list[dict]:
    cues = LABEL_CUES.get(metric, ())
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    hits: list[dict] = []
    for index, line in enumerate(lines):
        lower = line.lower()
        if not any(cue in lower for cue in cues):
            continue
        nums = _NUM.findall(line)
        # Prefer same-line numbers; else peek next line.
        if not nums and index + 1 < len(lines):
            nums = _NUM.findall(lines[index + 1])
        for raw in nums[:4]:
            hits.append({"line": line, "raw_source_value": raw, "evidence_text": line[:240]})
    return hits


def main() -> int:
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
    by_id = {item["filing_version_id"]: item for item in identity["items"]}
    filled = 0
    skipped = 0
    ambiguous = 0
    missing_pdf = 0
    per_filing: dict[str, dict] = {}

    for slot in queue.get("slots", queue.get("items", [])):
        if not isinstance(slot, dict):
            continue
        fid = slot.get("filing_version_id")
        metric = slot.get("metric_code")
        if not fid or not metric:
            continue
        meta = by_id.get(fid)
        if meta is None:
            skipped += 1
            continue
        pdf = ROOT / meta["local_file"]
        filing_stats = per_filing.setdefault(
            fid,
            {"filled": 0, "ambiguous": 0, "missing_pdf": 0, "slots": 0},
        )
        filing_stats["slots"] += 1
        if not pdf.is_file():
            missing_pdf += 1
            filing_stats["missing_pdf"] += 1
            slot["adjudication_status"] = "PDF_MISSING"
            continue
        # Never overwrite an already human-filled value.
        if slot.get("raw_source_value") not in (None, "", "null"):
            filled += 1
            filing_stats["filled"] += 1
            continue
        text = _pdf_text(pdf)
        hits = _find_candidates(text, metric)
        if len(hits) == 1:
            hit = hits[0]
            slot["raw_source_value"] = hit["raw_source_value"]
            slot["raw_source_label"] = hit["line"][:120]
            slot["evidence_text"] = hit["evidence_text"]
            slot["evidence_level"] = "LINE_TEXT_LAYER"
            slot["adjudication_status"] = "AUTO_PDF_CANDIDATE_NEEDS_HUMAN_CONFIRM"
            slot["reviewer_1"] = "pdf-text-layer-assist"
            slot["notes"] = (
                "Auto-filled from unique PDF text-layer label+number cue. "
                "NOT locked gold — requires human confirmation before V02."
            )
            filled += 1
            filing_stats["filled"] += 1
        elif len(hits) > 1:
            ambiguous += 1
            filing_stats["ambiguous"] += 1
            slot["adjudication_status"] = "AMBIGUOUS_PDF_CANDIDATES"
            slot["notes"] = f"{len(hits)} candidate lines; left null for human N17."
        else:
            skipped += 1
            slot["adjudication_status"] = slot.get("adjudication_status") or "PENDING_HUMAN"

    QUEUE.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    progress = {
        "id": "n17-blind-adjudication-progress",
        "recovery_step": "V01",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gold_locked": False,
        "note": (
            "PDF-text-layer assist only. Values marked AUTO_PDF_CANDIDATE_NEEDS_HUMAN_CONFIRM "
            "are not locked gold. Do not run N18 until human lock (V02)."
        ),
        "summary": {
            "filled_or_confirmed": filled,
            "ambiguous": ambiguous,
            "pending_or_skipped": skipped,
            "missing_pdf": missing_pdf,
            "by_status": dict(Counter(
                slot.get("adjudication_status") or "UNKNOWN"
                for slot in queue.get("slots", queue.get("items", []))
                if isinstance(slot, dict)
            )),
        },
        "per_filing": per_filing,
    }
    PROGRESS.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(progress["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
